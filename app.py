from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import subprocess
import re
import os
import stat as _stat
import pwd
import grp as _grp

app = FastAPI()

# =====================================================================
# MIDDLEWARE CORS
# =====================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================================
# ROUTE UTAMA — Dashboard saat pertama kali dibuka
# =====================================================================
@app.get("/")
async def read_index():
    return FileResponse("MANUX_dashboard.html")


# =====================================================================
# CATATAN KONFIGURASI SUDO
# =====================================================================
# Semua perintah privileged di bawah ini TIDAK menggunakan flag -S atau
# input password (subprocess input=...). Ini SENGAJA, karena server
# diasumsikan berjalan sebagai user yang sudah dikonfigurasi NOPASSWD
# di /etc/sudoers.d/manux, misalnya:
#
#   elpa-padila ALL=(ALL) NOPASSWD: /usr/sbin/useradd, /usr/sbin/userdel, \
#       /usr/sbin/usermod, /usr/sbin/groupadd, /usr/sbin/groupdel, \
#       /usr/sbin/chpasswd, /usr/bin/chfn, /usr/bin/chmod, /usr/bin/tail
#
# Menggunakan -S bersama NOPASSWD justru menyebabkan perintah gagal diam-diam
# karena stdin yang dikirim tidak diharapkan oleh sudo.


# =====================================================================
# MODELS
# =====================================================================
class UserForm(BaseModel):
    username: str
    fullname: str
    email: str
    role: str       # diisi sama dengan group dari frontend (role = group)
    group: str
    password: str


class GroupForm(BaseModel):
    name: str
    gid: int | None = None


class GroupMemberForm(BaseModel):
    group: str
    username: str


class ChmodForm(BaseModel):
    path: str
    mode: str


# =====================================================================
# HELPER: validasi nama linux (username/groupname)
# =====================================================================
LINUX_NAME_RE = re.compile(r'^[a-z_][a-z0-9_-]{0,31}$')

def is_valid_linux_name(name: str) -> bool:
    return bool(LINUX_NAME_RE.match(name or ""))


# =====================================================================
# ENDPOINT: STATS RINGKAS (dipakai halaman User Management lama)
# =====================================================================
@app.get("/get-stats")
async def get_stats():
    try:
        cmd_self = "whoami"
        res_self = subprocess.run(cmd_self, shell=True, capture_output=True, text=True)
        self_iden = res_self.stdout.strip() if res_self.returncode == 0 else "unknown"

        cmd_total = """awk -F: '$3 >= 1000 && $3 != 65534 {print $1}' /etc/passwd | wc -l"""
        res_total = subprocess.run(cmd_total, shell=True, capture_output=True, text=True)
        total_user = res_total.stdout.strip() if res_total.returncode == 0 else "0"

        cmd_online = "users | wc -w"
        res_online = subprocess.run(cmd_online, shell=True, capture_output=True, text=True)
        online = res_online.stdout.strip() if res_online.returncode == 0 else "0"

        cmd_admin = r"""grep '^sudo:' /etc/group | cut -d: -f4 | tr ',' '\n' | grep -v '^$' | wc -l"""
        res_admin = subprocess.run(cmd_admin, shell=True, capture_output=True, text=True)
        admin_stdout = res_admin.stdout.strip()
        admin_count = int(admin_stdout) + 1 if admin_stdout.isdigit() else 1

        cmd_new = "find /home -maxdepth 1 -mindepth 1 -ctime -7 | wc -l"
        res_new = subprocess.run(cmd_new, shell=True, capture_output=True, text=True)
        new_users = res_new.stdout.strip() if res_new.returncode == 0 else "0"

        return {
            "self": self_iden,
            "status": "success",
            "total_user": total_user,
            "online": online,
            "admin": admin_count,
            "new_user": new_users,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backend Error: {str(e)}")


# =====================================================================
# ENDPOINT: TAMBAH USER BARU
# =====================================================================
@app.post("/add-user-complete")
async def add_user_complete(form_data: UserForm):
    uname  = form_data.username
    passwd = form_data.password
    fname  = form_data.fullname
    gname  = form_data.group.strip()
    role   = gname  # role = group (dropdown role dihapus dari UI)

    if not is_valid_linux_name(uname):
        raise HTTPException(status_code=400, detail="Username tidak valid.")
    if not is_valid_linux_name(gname):
        raise HTTPException(status_code=400, detail="Nama grup tidak valid.")
    if not fname or len(fname) > 128:
        raise HTTPException(status_code=400, detail="Nama lengkap tidak valid.")
    if len(passwd) < 8:
        raise HTTPException(status_code=400, detail="Password minimal 8 karakter.")

    try:
        # A. Pastikan grup tujuan memang ada di Linux (buat otomatis jika belum)
        check_group = subprocess.run(f"getent group {gname}", shell=True, capture_output=True, text=True)
        if check_group.returncode != 0:
            subprocess.run(f"sudo groupadd {gname}", shell=True, capture_output=True, text=True)

        # B. Buat user — Primary Group = gname (pilihan dropdown Group di form)
        cmd_create = f'sudo useradd -m -g {gname} -c "{fname}" {uname}'
        res1 = subprocess.run(cmd_create, shell=True, capture_output=True, text=True)
        if res1.returncode != 0:
            return {"status": "failed", "error": res1.stderr.strip()}

        # C. Set password via chpasswd — stdin HANYA "user:pass" (NOPASSWD aktif)
        subprocess.run("sudo chpasswd", shell=True, capture_output=True, text=True,
                        input=f"{uname}:{passwd}\n", timeout=10)

        # D. Role "admin" → tambahkan ke grup 'sudo' sebagai secondary group
        if role == "admin":
            subprocess.run(f"sudo usermod -aG sudo {uname}", shell=True,
                            capture_output=True, text=True)

        return {
            "status": "success",
            "message": (
                f"User '{uname}' ({fname}) berhasil dibuat — Primary group: {gname}"
                + (", Secondary group: sudo" if role == "admin" else "")
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal eksekusi Linux: {str(e)}")


# =====================================================================
# ENDPOINT: AMBIL SEMUA USER
# =====================================================================
@app.get("/get-users")
async def get_users():
    try:
        cmd_users = """awk -F: '$3 >= 1000 && $3 != 65534 {print $1":"$5}' /etc/passwd"""
        res_users = subprocess.run(cmd_users, shell=True, capture_output=True, text=True)
        if res_users.returncode != 0:
            return {"status": "failed", "error": res_users.stderr.strip()}

        raw_users = res_users.stdout.strip().split("\n")

        cmd_online = "users"
        res_online = subprocess.run(cmd_online, shell=True, capture_output=True, text=True)
        online_users = res_online.stdout.strip().split()

        user_list = []
        for line in raw_users:
            if not line:
                continue
            username, fullname_raw = line.split(":", 1)
            fullname = fullname_raw.split(",")[0] if fullname_raw else username

            cmd_user_groups = f"groups {username}"
            res_ug = subprocess.run(cmd_user_groups, shell=True, capture_output=True, text=True)
            user_groups = res_ug.stdout.strip().split(":")[1].split() if res_ug.returncode == 0 and ":" in res_ug.stdout else []

            status = "online" if username in online_users else "offline"

            if "sudo" in user_groups or username in ["admin", "root"]:
                role = "admin"
                group_display = "admin"
            elif "dev" in user_groups:
                role = "dev"
                group_display = "dev"
            elif "ops" in user_groups:
                role = "ops"
                group_display = "ops"
            else:
                role = "viewer"
                group_display = "viewer"

            user_list.append({
                "username": username,
                "fullname": fullname,
                "role": role,
                "group": group_display,
                "status": status,
            })

        return {"status": "success", "users": user_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil user Linux: {str(e)}")


# =====================================================================
# ENDPOINT: HAPUS USER
# =====================================================================
@app.delete("/delete-user/{username}")
async def delete_user(username: str):
    if username in ["root", "admin"]:
        raise HTTPException(status_code=400, detail="User sistem utama tidak boleh dihapus!")

    try:
        cmd_delete = f"sudo userdel -r {username}"
        res = subprocess.run(cmd_delete, shell=True, capture_output=True, text=True, timeout=15)

        if res.returncode == 0:
            return {"status": "success", "message": f"User {username} berhasil dihapus dari sistem."}
        else:
            err_msg = (res.stderr.strip() or res.stdout.strip() or f"returncode={res.returncode}")
            return {"status": "failed", "error": err_msg}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Perintah userdel timeout — cek konfigurasi sudo/visudo.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal eksekusi perintah hapus di Linux: {str(e)}")


# =====================================================================
# ENDPOINT: EDIT USER (nama lengkap & grup)
# =====================================================================
@app.put("/edit-user-complete")
async def edit_user_complete(form_data: UserForm):
    uname = form_data.username
    fname = form_data.fullname
    gname = form_data.group.strip()
    role  = gname  # role = group

    if not is_valid_linux_name(uname):
        raise HTTPException(status_code=400, detail="Username tidak valid.")
    if not fname or len(fname) > 128:
        raise HTTPException(status_code=400, detail="Nama lengkap tidak valid.")

    try:
        # 1. Update Nama Lengkap via chfn
        cmd_edit = f'sudo chfn -f "{fname}" {uname}'
        subprocess.run(cmd_edit, shell=True, capture_output=True, text=True)

        # 2. Update Primary Group
        if gname and is_valid_linux_name(gname):
            if role == "admin":
                subprocess.run(f"sudo usermod -g sudo {uname}", shell=True, capture_output=True, text=True)
            else:
                # Buat grup otomatis jika belum ada
                check_group = subprocess.run(f"getent group {gname}", shell=True, capture_output=True, text=True)
                if check_group.returncode != 0:
                    subprocess.run(f"sudo groupadd {gname}", shell=True, capture_output=True, text=True)
                subprocess.run(f"sudo usermod -g {gname} {uname}", shell=True, capture_output=True, text=True)

        return {"status": "success", "message": f"Data user {uname} berhasil diperbarui!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengubah data Linux: {str(e)}")


# =====================================================================
# ENDPOINT: AMBIL SEMUA GRUP (GID >= 1000)
# =====================================================================
@app.get("/get-groups")
async def get_groups():
    try:
        cmd_groups = "awk -F: '$3 >= 1000 {print $1\":\"$3\":\"$4}' /etc/group"
        res = subprocess.run(cmd_groups, shell=True, capture_output=True, text=True)
        if res.returncode != 0:
            return {"status": "failed", "error": res.stderr.strip()}

        cmd_users = "awk -F: '$3 >= 1000 && $3 != 65534 {print $1}' /etc/passwd"
        res_users = subprocess.run(cmd_users, shell=True, capture_output=True, text=True)
        all_users = res_users.stdout.strip().split("\n") if res_users.returncode == 0 else []

        group_list = []
        for line in res.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(":")
            if len(parts) < 3:
                continue
            gname, gid_str, members_raw = parts[0], parts[1], parts[2]
            secondary_members = [m for m in members_raw.split(",") if m]

            cmd_primary = f"awk -F: '$4 == {gid_str} {{print $1}}' /etc/passwd"
            res_primary = subprocess.run(cmd_primary, shell=True, capture_output=True, text=True)
            primary_members = [u for u in res_primary.stdout.strip().split("\n") if u]

            all_members_set = list(dict.fromkeys(primary_members + secondary_members))
            members = [{"u": u, "role": "owner" if i == 0 else "member"} for i, u in enumerate(all_members_set)]

            group_list.append({
                "id": int(gid_str),
                "name": gname,
                "gid": int(gid_str),
                "members": members,
                "desc": "",
            })

        return {"status": "success", "groups": group_list, "all_users": all_users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal membaca grup Linux: {str(e)}")


# =====================================================================
# ENDPOINT: BUAT GRUP BARU
# =====================================================================
@app.post("/add-group")
async def add_group(form_data: GroupForm):
    if not is_valid_linux_name(form_data.name):
        raise HTTPException(status_code=400, detail="Nama grup tidak valid. Gunakan huruf kecil, angka, - atau _")

    try:
        gid_flag = f"-g {form_data.gid}" if form_data.gid else ""
        cmd = f"sudo groupadd {gid_flag} {form_data.name}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode != 0:
            return {"status": "failed", "error": res.stderr.strip()}

        cmd_gid = f"getent group {form_data.name} | cut -d: -f3"
        res_gid = subprocess.run(cmd_gid, shell=True, capture_output=True, text=True)
        new_gid = int(res_gid.stdout.strip()) if res_gid.stdout.strip().isdigit() else 0

        return {"status": "success", "message": f"Grup '{form_data.name}' berhasil dibuat (GID {new_gid}).", "gid": new_gid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal membuat grup: {str(e)}")


# =====================================================================
# ENDPOINT: TAMBAH MEMBER KE GRUP
# =====================================================================
@app.post("/add-group-member")
async def add_group_member(form_data: GroupMemberForm):
    try:
        cmd = f"sudo usermod -aG {form_data.group} {form_data.username}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode != 0:
            return {"status": "failed", "error": res.stderr.strip()}
        return {"status": "success", "message": f"User '{form_data.username}' berhasil ditambahkan ke grup '{form_data.group}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menambahkan member: {str(e)}")


# =====================================================================
# ENDPOINT: HAPUS GRUP
# =====================================================================
@app.delete("/delete-group/{name}")
async def delete_group(name: str):
    PROTECTED = ["root", "sudo", "admin", "shadow", "staff", "nogroup", "daemon", "bin", "sys", "www-data"]
    if name in PROTECTED:
        raise HTTPException(status_code=400, detail=f"Grup sistem '{name}' tidak boleh dihapus!")

    try:
        cmd = f"sudo groupdel {name}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode != 0:
            return {"status": "failed", "error": res.stderr.strip()}
        return {"status": "success", "message": f"Grup '{name}' berhasil dihapus dari sistem."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menghapus grup: {str(e)}")


# =====================================================================
# ENDPOINT: DASHBOARD — stat gabungan (user + group)
# =====================================================================
@app.get("/get-dashboard")
async def get_dashboard():
    try:
        r_total = subprocess.run(
            "awk -F: '$3>=1000&&$3!=65534{print $1}' /etc/passwd | wc -l",
            shell=True, capture_output=True, text=True)
        total_user = int(r_total.stdout.strip() or 0)

        r_who = subprocess.run("users", shell=True, capture_output=True, text=True)
        online_set = set(r_who.stdout.strip().split()) if r_who.stdout.strip() else set()
        online = len(online_set)

        r_grp = subprocess.run(
            "awk -F: '$3>=1000{print $1}' /etc/group | wc -l",
            shell=True, capture_output=True, text=True)
        total_groups = int(r_grp.stdout.strip() or 0)

        r_gnames = subprocess.run(
            "awk -F: '$3>=1000{print $1}' /etc/group | head -4",
            shell=True, capture_output=True, text=True)
        group_names = [g for g in r_gnames.stdout.strip().split("\n") if g]

        r_users = subprocess.run(
            "awk -F: '$3>=1000&&$3!=65534{print $1}' /etc/passwd | head -6",
            shell=True, capture_output=True, text=True)
        user_list = []
        for uname in [u for u in r_users.stdout.strip().split("\n") if u]:
            r_gecos = subprocess.run(f"getent passwd {uname}", shell=True, capture_output=True, text=True)
            gecos_parts = r_gecos.stdout.strip().split(":") if r_gecos.returncode == 0 else []
            fname = (gecos_parts[4].split(",")[0] if len(gecos_parts) > 4 and gecos_parts[4] else uname)
            r_ug = subprocess.run(f"groups {uname}", shell=True, capture_output=True, text=True)
            grps = r_ug.stdout.strip().split(":")[1].split() if r_ug.returncode == 0 and ":" in r_ug.stdout else []
            grp_display = "sudo" if "sudo" in grps else (grps[0] if grps else "-")
            user_list.append({
                "username": uname,
                "fullname": fname,
                "group": grp_display,
                "status": "online" if uname in online_set else "offline",
            })

        r_self = subprocess.run("whoami", shell=True, capture_output=True, text=True)
        return {
            "status": "success",
            "self": r_self.stdout.strip(),
            "total_user": total_user,
            "online": online,
            "total_groups": total_groups,
            "group_names": group_names,
            "users": user_list,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# ENDPOINT: ACTIVITY LOG — baca /var/log/auth.log
# =====================================================================
# =====================================================================
# ENDPOINT: ACTIVITY LOG — baca /var/log/auth.log (VERSI TERJEMAHAN UI MODERN)
# =====================================================================
@app.get("/get-activity-log")
async def get_activity_log():
    try:
        r = subprocess.run("sudo tail -200 /var/log/auth.log",
                            shell=True, capture_output=True, text=True, timeout=10)
        if r.returncode != 0 or not r.stdout.strip():
            r = subprocess.run("tail -200 /var/log/auth.log",
                                shell=True, capture_output=True, text=True, timeout=10)

        ip_pat   = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})')
        sess_pat = re.compile(r'(pts/\d+|tty\d+)')
        user_pat = re.compile(r'(?:user|for|by|USER=)\s+(\S+)', re.I)

        line_pat_iso = re.compile(
            r'^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}:\d{2})\.\d+[+-]\d{2}:\d{2}\s+\S+\s+(\S+?)(?:\[\d+\])?\s*:\s*(.+)$'
        )
        line_pat_classic = re.compile(
            r'^(\w{3}\s+\d+\s+\d+:\d+:\d+)\s+\S+\s+(\S+?)(?:\[\d+\])?\s*:\s*(.+)$'
        )

        logs = []
        for line in (r.stdout or "").strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            m_iso = line_pat_iso.match(line)
            if m_iso:
                ts, service, msg = m_iso.groups()
            else:
                m_classic = line_pat_classic.match(line)
                if not m_classic:
                    continue
                ts_raw, service, msg = m_classic.groups()
                ts = ts_raw[-8:]

            msg_l = msg.lower()

            # 🌟 1. LOGIKA UTAMA: PENERJEMAH BAHASA KERNEL LINUX KE BAHASA MANUSIA
            # Default awal jika tidak masuk kriteria filter terjemahan
            display_desc = msg[:120] 
            sev, typ = "info", "login"

            # Kategori: Kegagalan Autentikasi / Error
            if "conversation failed" in msg_l or "could not identify password" in msg_l:
                display_desc = "Login gagal 3x berturut-turut"
                sev, typ = "error", "login"
            elif "authentication failure" in msg_l:
                display_desc = "Autentikasi gagal — Password salah"
                sev, typ = "error", "login"
            
            # Kategori: Sesi Otomatis Cron Job Sistem
            elif "cron:session" in msg_l:
                typ = "login"  # Agar masuk ke penghitung login di UI stat
                if "opened" in msg_l:
                    display_desc = "Sesi sistem otomatis (Cron Job) dimulai"
                    sev = "success"
                else:
                    display_desc = "Sesi sistem otomatis (Cron Job) selesai"
                    sev = "info"

            # Kategori: Perintah Administratif Sudo (User, Group, Visudo, Chmod)
            elif "visser" in msg_l or "visudo" in msg_l:
                display_desc = "Membuka editor keamanan visudo (akses root)"
                sev, typ = "warning", "permission"
            elif "useradd" in msg_l:
                display_desc = f"User baru berhasil ditambahkan ke sistem"
                sev, typ = "success", "user"
            elif "userdel" in msg_l:
                display_desc = f"User berhasil dihapus dari sistem"
                sev, typ = "success", "user"
            elif "groupadd" in msg_l:
                display_desc = "Grup baru berhasil dibuat"
                sev, typ = "success", "group"
            elif "groupdel" in msg_l:
                display_desc = "Grup berhasil dihapus dari sistem"
                sev, typ = "success", "group"
            elif "chmod" in msg_l:
                # Mengambil informasi chmod rapi dari log command sudo jika ada
                if "command=" in msg_l:
                    cmd_part = msg.split("COMMAND=")[-1]
                    display_desc = f"{cmd_part} pada file sistem"
                else:
                    display_desc = "Hak akses file/direktori (chmod) diubah"
                sev, typ = "warning", "permission"
            
            # Kategori: Login Berhasil Umum
            elif "accepted" in msg_l or "session opened" in msg_l:
                display_desc = "Login berhasil — Sesi baru dimulai"
                sev, typ = "success", "login"
            elif "session closed" in msg_l or "closed" in msg_l:
                display_desc = "Sesi ditutup — User logout"
                sev, typ = "info", "login"

            # Koreksi deteksi dasar bawaan agar filter tipe tetap sinkron
            if typ == "login" and any(x in msg_l for x in ["failed", "error"]):
                sev = "error"

            um = user_pat.search(msg)
            user = um.group(1).rstrip(";") if um else service
            
            # Bersihkan nama user sistem agar tampilan di UI "Clean"
            if user in ["sudo", "systemd-logind", "sshd", "cron"]:
                if "elpa-padila" in msg_l:
                    user = "elpa-padila"
                elif "root" in msg_l:
                    user = "root"
                else:
                    user = "system"

            ip_m = ip_pat.search(msg)
            sess_m = sess_pat.search(msg)

            logs.append({
                "time": ts[-8:],
                "user": user,
                "type": typ,
                "sev": sev,
                "desc": display_desc, # 🌟 Menggunakan hasil terjemahan kita
                "ip": ip_m.group(1) if ip_m else "localhost",
                "cmd": service,
                "session": sess_m.group(1) if sess_m else "-",
            })

        logs.reverse()
        return {"status": "success", "logs": logs[:100]}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="auth.log timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# ENDPOINT: PERMISSIONS — baca permission real via os.stat
# =====================================================================
PERM_PATHS = [
    "/etc/passwd", "/etc/shadow", "/etc/group",
    "/var/log", "/tmp", "/home",
    "/usr/bin/bash", "/usr/bin/sudo", "/etc/sudoers",
]

@app.get("/get-permissions")
async def get_permissions():
    result = []
    for i, path in enumerate(PERM_PATHS):
        try:
            st = os.stat(path)
            mode = st.st_mode
            o = (mode >> 6) & 7
            g = (mode >> 3) & 7
            p = mode & 7
            ftype = ("dir" if _stat.S_ISDIR(mode)
                      else "script" if any(path.endswith(x) for x in ["bash", "sudo", "sh"])
                      else "file")
            try:
                owner_name = pwd.getpwuid(st.st_uid).pw_name
            except Exception:
                owner_name = str(st.st_uid)
            try:
                group_name = _grp.getgrgid(st.st_gid).gr_name
            except Exception:
                group_name = str(st.st_gid)
            result.append({
                "id": i + 1, "name": path, "type": ftype,
                "owner": owner_name, "group": group_name,
                "perm": [o, g, p], "changed": False,
            })
        except PermissionError:
            result.append({
                "id": i + 1, "name": path, "type": "file",
                "owner": "?", "group": "?", "perm": [0, 0, 0], "changed": False,
            })
        except FileNotFoundError:
            pass
    return {"status": "success", "resources": result}


# =====================================================================
# ENDPOINT: APPLY CHMOD — terapkan chmod ke path di PERM_PATHS
# =====================================================================
@app.post("/apply-chmod")
async def apply_chmod(form: ChmodForm):
    LOCKED = ["/etc/passwd", "/etc/shadow", "/etc/sudoers"]
    if form.path not in PERM_PATHS:
        raise HTTPException(status_code=400, detail="Path tidak diizinkan.")
    if not re.match(r'^[0-7]{3}$', form.mode):
        raise HTTPException(status_code=400, detail="Mode chmod tidak valid.")
    if form.path in LOCKED:
        raise HTTPException(status_code=403, detail=f"'{form.path}' terkunci — tidak dapat diubah dari UI.")
    try:
        res = subprocess.run(f"sudo chmod {form.mode} {form.path}",
                              shell=True, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return {"status": "success", "message": f"chmod {form.mode} {form.path} berhasil."}
        return {"status": "failed", "error": res.stderr.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# STATIC FILES (HARUS DI BAWAH SEMUA ROUTE API)
# =====================================================================
app.mount("/static", StaticFiles(directory="."), name="static")


if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)