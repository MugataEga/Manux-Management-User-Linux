from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Struktur data input jika kamu masih butuh endpoint POST /run-command secara dinamis
class CommandRequest(BaseModel):
    command: str

@app.post("/run-command")
async def run_command(request: CommandRequest):
    perintah_pilihan = request.command
    allowed_commands = {
    }
    
    if perintah_pilihan not in allowed_commands:
        raise HTTPException(status_code=400, detail="Perintah tidak diizinkan atau tidak ditemukan.")
    
    try:
        result = subprocess.run(allowed_commands[perintah_pilihan], capture_output=True, text=True, shell=True)
        return {
            "status": "success",
            "output": result.stdout if result.returncode == 0 else result.stderr
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)