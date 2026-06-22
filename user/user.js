const COLORS = ['u-blue','u-teal','u-amber','u-purple','u-coral','u-green'];

const ROLE_PILL = {
  admin: 'p-admin',
  dev: 'p-dev',
  ops: 'p-ops',
  viewer: 'p-viewer'
};

const STATUS_PILL = {
  online: 'p-online',
  idle: 'p-idle',
  offline: 'p-offline'
};

// Array lokal murni kembali utuh untuk mengelola state internal dashboard
let users = [];
let nextId = 1;
let editingId = null;
let deleteTargetId = null;
let filtered = [];

/* ================= UTIL ================= */
function initials(n) {
  if (!n) return 'UN';
  return n.split(' ').slice(0,2).map(w => w[0]).join('').toUpperCase();
}

/* ================= AMBIL DATA DARI BACKEND ================= */
async function fetchUsersFromBackend() {
  try {
    const response = await fetch('http://127.0.0.1:5000/get-users');
    const data = await response.json();
    
    if (data.status === 'success') {
      // Map data dari Linux agar sesuai dengan format komponen UI HTML kalian
      users = data.users.map((u, index) => ({
        id: index + 1,
        username: u.username,
        name: u.fullname || u.username,
        email: `${u.username}@manux.dev`,
        role: u.role,
        group: u.group,
        status: u.status,
        isNew: false
      }));
      filtered = [...users];
      renderTable(); // Jalankan fungsi render bawaan user.js asli
    } else {
      console.error("Gagal mengambil data Linux:", data.error);
    }
  } catch (error) {
    console.error("Gagal terhubung ke Backend FastAPI:", error);
  }
}

async function fetchStatsFromBackend() {
  try {
    const response = await fetch('http://127.0.0.1:5000/get-stats');
    const data = await response.json();
    
    if (data.status === 'success') {
      if(document.getElementById('st-total')) document.getElementById('st-total').textContent = data.total_user;
      if(document.getElementById('st-online')) document.getElementById('st-online').textContent = data.online;
      if(document.getElementById('st-admin')) document.getElementById('st-admin').textContent = data.admin;
      if(document.getElementById('st-new')) document.getElementById('st-new').textContent = data.new_user;
    }
  } catch (error) {
    console.error("Gagal mengambil statistik Linux:", error);
  }
}

/* ================= POPULATE GROUP DROPDOWN ================= */
/**
 * Menembak GET /get-groups, lalu mengisi <select id="f-group">
 * dengan nama grup asli Linux (GID >= 1000).
 * Dipanggil saat inisialisasi dashboard dan saat form di-reset.
 */
async function populateGroupDropdown() {
  const sel = document.getElementById('f-group');
  if (!sel) return;
  sel.innerHTML = '<option value="">⏳ Memuat grup...</option>';
  sel.disabled = true;
  try {
    const res  = await fetch('http://127.0.0.1:5000/get-groups');
    const data = await res.json();
    if (data.status === 'success' && data.groups.length) {
      sel.innerHTML = '<option value="">Pilih Group...</option>';
      data.groups.forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.name;
        opt.textContent = `${g.name}  (GID ${g.gid})`;
        sel.appendChild(opt);
      });
    } else {
      sel.innerHTML = '<option value="">Tidak ada grup tersedia</option>';
    }
  } catch (e) {
    console.error('Gagal memuat grup:', e);
    sel.innerHTML = '<option value="">Gagal memuat grup</option>';
  } finally {
    sel.disabled = false;
  }
}

/* ================= RENDER ORIGINAL ================= */
function renderTable() {
  const tbody = document.getElementById('user-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  filtered.forEach((u) => {
    const color = COLORS[u.id % COLORS.length];
    const tr = document.createElement('tr');

    if (editingId === u.id) tr.classList.add('selected-row');

    // Menggunakan kelas visual asli bawaan file user.js pertamamu
    tr.innerHTML = `
      <td>
        <div class="ua ${color} initial" style="margin:0 auto;">
          ${initials(u.name)}
        </div>
      </td>
      <td>
        <div class="username">${u.username}</div>
        <div class="ps">${u.name}</div>
      </td>
      <td class="role">${u.role}</td>
      <td class="group">${u.group}</td>
      <td>
        <span class="status ${u.status}">${u.status}</span>
      </td>
      <td>
        <div class="action-btns">
          <button class="ab ab-edit" onclick="openEdit(${u.id})">Edit</button>
          <button class="ab ab-del" onclick="openDelete(${u.id}, '${u.username}')"
            ${u.username === 'admin' || u.username === 'root' || u.username === 'elpa-padila' ? 'disabled style="opacity:.4;cursor:not-allowed;"' : ''}>
            Del
          </button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });

  const tblCount = document.getElementById('tbl-count');
  if (tblCount) tblCount.textContent = `Menampilkan ${filtered.length} user`;
}

/* ================= FILTER ================= */
function filterTable() {
  const q = document.getElementById('search-inp').value.toLowerCase();
  const s = document.getElementById('filter-status').value;

  filtered = users.filter(u => {
    const matchQ = !q || u.username.includes(q) || u.name.toLowerCase().includes(q);
    const matchS = s === 'all' || u.status === s;
    return matchQ && matchS;
  });

  renderTable();
}

/* ================= FORM SUBMIT (TERHUBUNG KE LINUX) ================= */
/* ================= FORM SUBMIT (TERHUBUNG KE LINUX) ================= */
async function submitForm() {
  const uname = document.getElementById('f-username').value.trim();
  const fname = document.getElementById('f-fullname').value.trim();
  const email = document.getElementById('f-email') ? document.getElementById('f-email').value.trim() : '';
  const group = (document.getElementById('f-group').value || '').trim();
  const role  = group; // role = group (tidak ada dropdown role terpisah)
  const pass  = document.getElementById('f-pass').value;

  if (!uname || !fname || (editingId === null && (!group || pass.length < 8))) {
    showToast('Lengkapi semua field yang wajib diisi!', 'err');
    return;
  }

  if (editingId === null) {
    // ================= MODE: TAMBAH USER BARU =================
    showToast('Sedang membuat user di sistem Linux...', 'ok');
    try {
      const response = await fetch('http://127.0.0.1:5000/add-user-complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: uname,
          fullname: fname,
          email: email,
          role: role,
          group: group,
          password: pass
        })
      });
      
      const resData = await response.json();
      if (resData.status === 'success') {
        showToast(`User Linux ${uname} sukses diciptakan!`, 'ok');
        resetForm();
        initDashboard();
      } else {
        showToast('Gagal: ' + resData.error, 'err');
      }
    } catch (e) {
      showToast('Gagal menghubungi backend server!', 'err');
    }
  } else {
    // ================= MODE: EDIT USER (SIMPAN PERUBAHAN) =================
    showToast('Sedang memperbarui data di sistem Linux...', 'ok');
    try {
      const response = await fetch('http://127.0.0.1:5000/edit-user-complete', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: uname,
          fullname: fname,
          email: email,
          role: role,
          group: group,
          password: 'skip_password_fields' // Mengisi skema pydantic agar lolos validasi
        })
      });
      
      const resData = await response.json();
      if (resData.status === 'success') {
        showToast(`Data user ${uname} sukses diperbarui!`, 'ok');
        editingId = null;
        resetForm();
        initDashboard(); // Refresh tabel agar nama baru langsung muncul
      } else {
        showToast('Gagal edit: ' + resData.error, 'err');
      }
    } catch (e) {
      showToast('Gagal menghubungi backend server saat edit!', 'err');
    }
  }
}

function openAddForm() {
  editingId = null;
  if(document.getElementById('form-title')) document.getElementById('form-title').textContent = 'Tambah user baru';
  if(document.getElementById('btn-submit-label')) document.getElementById('btn-submit-label').textContent = 'Tambah user';
  if(document.getElementById('f-username')) { document.getElementById('f-username').value = ''; document.getElementById('f-username').disabled = false; }
  if(document.getElementById('f-fullname')) document.getElementById('f-fullname').value = '';
  if(document.getElementById('f-email')) document.getElementById('f-email').value = '';
  if(document.getElementById('f-pass')) document.getElementById('f-pass').value = '';
  // Refresh dropdown grup dari Linux setiap kali form dibuka
  populateGroupDropdown();
  clearToast();
}

function openEdit(id) {
  const u = users.find(x => x.id === id);
  if (!u) return;
  editingId = id;
  if(document.getElementById('form-title')) document.getElementById('form-title').textContent = 'Edit user: ' + u.username;
  if(document.getElementById('btn-submit-label')) document.getElementById('btn-submit-label').textContent = 'Simpan perubahan';
  if(document.getElementById('f-username')) { document.getElementById('f-username').value = u.username; document.getElementById('f-username').disabled = true; }
  if(document.getElementById('f-fullname')) document.getElementById('f-fullname').value = u.name;
  // Set dropdown group ke nilai saat ini
  const grpSel = document.getElementById('f-group');
  if(grpSel) grpSel.value = u.group;
  clearToast();
}

function validateForm() {
  const uInp = document.getElementById('f-username');
  const fInp = document.getElementById('f-fullname');
  const btnSub = document.getElementById('btn-submit');
  
  if(uInp && fInp && btnSub) {
    const ok = uInp.value.trim() && fInp.value.trim();
    btnSub.style.opacity = ok ? '1' : '0.55';
  }
}

function resetForm() {
  editingId = null;
  openAddForm();
}

/* ================= TOAST PLUGINS ================= */
function showToast(msg, type) {
  const t = document.getElementById('form-toast');
  if (!t) return;
  t.textContent = msg;
  t.className = 'toast ' + (type === 'ok' ? 'toast-ok' : 'toast-del');
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 3000);
}

function clearToast() {
  const t = document.getElementById('form-toast');
  if (t) t.style.display = 'none';
}

/* ================= INITIALIZATION ================= */
function initDashboard() {
  fetchUsersFromBackend();
  fetchStatsFromBackend();
  populateGroupDropdown();  // Isi dropdown grup dari Linux saat pertama load
}

window.addEventListener('DOMContentLoaded', () => {
  initDashboard();
  validateForm();
});

/* ================= KUNCI PERBAIKAN MODAL HAPUS ================= */
// Fungsi ini yang bertugas menjembatani tombol Del di tabel untuk membuka modal di HTML-mu
function openDelete(id, username) {
  if (typeof bukaModalHapus === 'function') {
    bukaModalHapus(username);
  }
}