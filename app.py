from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#buat bikin new user dari form data
class UserForm(BaseModel):
    username: str
    fullname: str
    email: str
    role: str
    group: str
    password: str

@app.get("/get-stats")
async def get_stats():
    try:
        # 0. Ambil Identitas User Login
        cmd_self = """wsl whoami"""
        res_self = subprocess.run(cmd_self, shell=True, capture_output=True, text=True)
        self_iden = res_self.stdout.strip() if res_self.returncode == 0 else "unknown"

        # 1. Total User
        cmd_total = """wsl awk -F: '$3 >= 1000 && $3 != 65534 {print $1}' /etc/passwd | wc -l"""
        res_total = subprocess.run(cmd_total, shell=True, capture_output=True, text=True)
        total_user = res_total.stdout.strip() if res_total.returncode == 0 else "0"

        # 2. User Online
        cmd_online = """wsl users | wc -w"""
        res_online = subprocess.run(cmd_online, shell=True, capture_output=True, text=True)
        online = res_online.stdout.strip() if res_online.returncode == 0 else "0"

        # 3. Jumlah Admin/Root
        # KOREKSI UTAMA: Tambahkan r sebelum triple quotes agar \n dibaca sebagai teks mentah oleh Python
        cmd_admin = r"""wsl grep '^sudo:' /etc/group | cut -d: -f4 | tr ',' '\n' | grep -v '^$' | wc -l"""
        res_admin = subprocess.run(cmd_admin, shell=True, capture_output=True, text=True)
        
        # Pengaman: Cek apakah outputnya benar-benar angka sebelum di-convert ke int
        admin_stdout = res_admin.stdout.strip()
        if admin_stdout.isdigit():
            admin_count = int(admin_stdout) + 1
        else:
            admin_count = 1  # Default hanya user root utama jika output bermasalah

        # 4. User Baru (7 Hari Terakhir)
        cmd_new = """wsl find /home -maxdepth 1 -mindepth 1 -ctime -7 | wc -l"""
        res_new = subprocess.run(cmd_new, shell=True, capture_output=True, text=True)
        new_users = res_new.stdout.strip() if res_new.returncode == 0 else "0"

        return {
            "self": self_iden,
            "status": "success",
            "total_user": total_user,
            "online": online,
            "admin": admin_count,
            "new_user": new_users
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backend Error: {str(e)}")

# Variabel session tiruan (pastikan login sudah mengisi ini, atau isi manual dulu buat tes)
SESSION_SUDO_PASSWORD = "harrypcm18" 

# 2. Daftarkan Endpoint POST Baru yang ditembak oleh JS Form
@app.post("/add-user-complete")
async def add_user_complete(form_data: UserForm):
    global SESSION_SUDO_PASSWORD
    if not SESSION_SUDO_PASSWORD:
        raise HTTPException(status_code=401, detail="Sesi admin habis, silakan login kembali.")

    uname = form_data.username
    passwd = form_data.password
    gname = form_data.group

    try:
        # Jalankan pembuatan user Linux secara berurutan
        # Perintah A: Buat user murni + set grup utama sesuai input
        cmd_create = f"wsl sudo -S useradd -m -g {gname} {uname}"
        res1 = subprocess.run(cmd_create, shell=True, capture_output=True, text=True, input=f"{SESSION_SUDO_PASSWORD}\n")
        if res1.returncode != 0:
            # Jika user sudah ada atau grup tidak terdaftar di Linux, return error agar ketahuan
            return {"status": "failed", "error": res1.stderr.strip()}

        # Perintah B: Set Password secara otomatis lewat chpasswd pipe
        cmd_pass = f"echo '{uname}:{passwd}' | wsl sudo -S chpasswd"
        subprocess.run(cmd_pass, shell=True, capture_output=True, text=True, input=f"{SESSION_SUDO_PASSWORD}\n")

        # Respons sukses kembali ke Frontend
        return {
            "status": "success", 
            "message": f"User {uname} berhasil dibuat pada grup {gname}!"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal eksekusi WSL: {str(e)}")
    
@app.get("/get-users")
async def get_users():
    try:
        # 1. Ambil user reguler (UID >= 1000) beserta kolom teks gecos/fullname
        cmd_users = """wsl awk -F: '$3 >= 1000 && $3 != 65534 {print $1":"$5}' /etc/passwd"""
        res_users = subprocess.run(cmd_users, shell=True, capture_output=True, text=True)
        if res_users.returncode != 0:
            return {"status": "failed", "error": res_users.stderr.strip()}

        raw_users = res_users.stdout.strip().split("\n")
        
        # 2. Ambil siapa saja user yang saat ini sedang aktif (online)
        cmd_online = """wsl users"""
        res_online = subprocess.run(cmd_online, shell=True, capture_output=True, text=True)
        online_users = res_online.stdout.strip().split()

        # 3. Ambil daftar grup dari /etc/group untuk memetakan kepemilikan grup
        cmd_groups = """wsl cat /etc/group"""
        res_groups = subprocess.run(cmd_groups, shell=True, capture_output=True, text=True)
        raw_groups = res_groups.stdout.strip().split("\n")

        user_list = []
        
        for line in raw_users:
            if not line: continue
            username, fullname_raw = line.split(":", 1)
            # Membersihkan koma bawaan dari field gecos Linux
            fullname = fullname_raw.split(",")[0] if fullname_raw else username
            
            # Cari tahu user ini masuk ke grup mana saja
            user_groups = []
            for g_line in raw_groups:
                if not g_line: continue
                g_parts = g_line.split(":")
                if len(g_parts) == 4 and username in g_parts[3].split(","):
                    user_groups.append(g_parts[0])
            
            # Tentukan status online/offline
            status = "online" if username in online_users else "offline"
            
            # Logika pencocokan Role kosmetik berdasarkan grup
            if "sudo" in user_groups or username == "admin":
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
                group_display = user_groups[0] if user_groups else "viewer"

            user_list.append({
                "username": username,
                "fullname": fullname,
                "role": role,
                "group": group_display,
                "status": status
            })

        return {"status": "success", "users": user_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil user Linux: {str(e)}")


# =====================================================================
# ENDPOINT BARU 2: HAPUS USER DARI WSL BERDASARKAN TOMBOL MODAL DI WEB
# =====================================================================
@app.delete("/delete-user/{username}")
async def delete_user(username: str):
    global SESSION_SUDO_PASSWORD
    if not SESSION_SUDO_PASSWORD:
        raise HTTPException(status_code=401, detail="Sesi admin habis, silakan login kembali.")

    # Proteksi darurat: Jangan biarkan user admin utama kamu terhapus secara tidak sengaja via web!
    if username in ["root", "admin"]:
        raise HTTPException(status_code=400, detail="User sistem utama / root tidak boleh dihapus!")

    try:
        # Perintah userdel -r akan menghapus user sekaligus membuang folder /home-nya secara bersih
        cmd_delete = f"wsl sudo -S userdel -r {username}"
        res = subprocess.run(cmd_delete, shell=True, capture_output=True, text=True, input=f"{SESSION_SUDO_PASSWORD}\n")
        
        if res.returncode == 0:
            return {"status": "success", "message": f"User {username} berhasil dimusnahkan dari sistem."}
        else:
            return {"status": "failed", "error": res.stderr.strip()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal eksekusi perintah hapus di WSL: {str(e)}")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)