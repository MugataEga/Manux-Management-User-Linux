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

let users = [
  {id:1,username:'admin',name:'Administrator',email:'admin@manux.dev',role:'admin',group:'admin',status:'online',isNew:false},
  {id:2,username:'mukgot',name:'Mukgot Ega S.',email:'mukgot@manux.dev',role:'dev',group:'dev',status:'online',isNew:false},
  {id:3,username:'safani',name:'Safani Nuraini',email:'safani@manux.dev',role:'ops',group:'ops',status:'idle',isNew:false},
  {id:4,username:'malik',name:'Malik Alfat M.',email:'malik@manux.dev',role:'dev',group:'dev',status:'offline',isNew:false},
  {id:5,username:'elpa',name:'Elpa Padila',email:'elpa@manux.dev',role:'viewer',group:'viewer',status:'offline',isNew:true},
  {id:6,username:'kirana',name:'Kirana Cinta M.',email:'kirana@manux.dev',role:'dev',group:'dev',status:'online',isNew:false},
  {id:7,username:'zaky',name:'Zaky Aditya S.',email:'zaky@manux.dev',role:'ops',group:'ops',status:'offline',isNew:true},
  {id:8,username:'adinda',name:'Adinda Syafira',email:'adinda@manux.dev',role:'viewer',group:'viewer',status:'offline',isNew:false},
];

let nextId = 9;
let editingId = null;
let deleteTargetId = null;
let filtered = [...users];

/* ================= UTIL ================= */
function initials(n) {
  return n.split(' ').slice(0,2).map(w => w[0]).join('').toUpperCase();
}

/* ================= RENDER ================= */
function renderTable() {
  const tbody = document.getElementById('user-tbody');
  tbody.innerHTML = '';

  filtered.forEach((u) => {
    const color = COLORS[u.id % COLORS.length];
    const tr = document.createElement('tr');

    if (editingId === u.id) tr.classList.add('selected-row');

    tr.innerHTML = `
      <td>
        <div class="ua ${color} initial" style="margin:0 auto;">
          ${initials(u.name)}
        </div>
      </td>

      <td>
        <div class="username">${u.username}</div>
        <div class="ps">
          ${u.name}
        </div>
      </td>
      <td class="role">
        ${u.role}
      </td>
      <td class="group">
        ${u.group}
      </td>
      <td>
        <span class="status ${u.status}">
          ${u.status}
        </span>
      </td>

      <td>
        <div class="action-btns">
          <button class="ab ab-edit" onclick="openEdit(${u.id})">
            Edit
          </button>

          <button class="ab ab-del"
            onclick="openDelete(${u.id})"
            ${u.username === 'admin' ? 'disabled style="opacity:.4;cursor:not-allowed;"' : ''}>
            Del
          </button>
        </div>
      </td>
    `;

    tbody.appendChild(tr);
  });

  document.getElementById('tbl-count').textContent =
    `Menampilkan ${filtered.length} user`;

  updateStats();
}

/* ================= STATS ================= */
function updateStats() {
  document.getElementById('st-total').textContent = users.length;
  document.getElementById('st-online').textContent = users.filter(u => u.status === 'online').length;
  document.getElementById('st-admin').textContent = users.filter(u => u.role === 'admin').length;
  document.getElementById('st-new').textContent = users.filter(u => u.isNew).length;
}

/* ================= FILTER ================= */
function filterTable() {
  const q = document.getElementById('search-inp').value.toLowerCase();
  const r = document.getElementById('filter-role').value;
  const s = document.getElementById('filter-status').value;

  filtered = users.filter(u => {
    const matchQ =
      !q ||
      u.username.includes(q) ||
      u.name.toLowerCase().includes(q) ||
      u.email.includes(q);

    const matchR = r === 'all' || u.role === r;
    const matchS = s === 'all' || u.status === s;

    return matchQ && matchR && matchS;
  });

  renderTable();
}

/* ================= FORM ================= */
function openAddForm() {
  editingId = null;

  document.getElementById('form-title').textContent = 'Tambah user baru';
  document.getElementById('btn-submit-label').textContent = 'Tambah user';

  document.getElementById('f-username').value = '';
  document.getElementById('f-fullname').value = '';
  document.getElementById('f-email').value = '';
  document.getElementById('f-role').value = '';
  document.getElementById('f-group').value = 'dev';
  document.getElementById('f-pass').value = '';

  document.getElementById('f-username').disabled = false;

  clearToast();
  renderTable();
}

function openEdit(id) {
  const u = users.find(x => x.id === id);
  if (!u) return;

  editingId = id;

  document.getElementById('form-title').textContent = 'Edit user: ' + u.username;
  document.getElementById('btn-submit-label').textContent = 'Simpan perubahan';

  document.getElementById('f-username').value = u.username;
  document.getElementById('f-fullname').value = u.name;
  document.getElementById('f-email').value = u.email;
  document.getElementById('f-role').value = u.role;
  document.getElementById('f-group').value = u.group;
  document.getElementById('f-pass').value = '';

  document.getElementById('f-username').disabled = true;

  clearToast();
  renderTable();
}

function validateForm() {
  const ok =
    document.getElementById('f-username').value.trim() &&
    document.getElementById('f-fullname').value.trim() &&
    (editingId || document.getElementById('f-pass').value.length >= 8);

  document.getElementById('btn-submit').style.opacity = ok ? '1' : '0.55';
}

function submitForm() {
  const uname = document.getElementById('f-username').value.trim();
  const fname = document.getElementById('f-fullname').value.trim();
  const email = document.getElementById('f-email').value.trim();
  const role = document.getElementById('f-role').value || 'viewer';
  const group = document.getElementById('f-group').value || 'dev';
  const pass = document.getElementById('f-pass').value;

  if (!uname || !fname || (editingId === null && pass.length < 8)) {
    showToast('Lengkapi semua field yang wajib diisi!', 'err');
    return;
  }

  if (editingId !== null) {
    const u = users.find(x => x.id === editingId);
    if (u) {
      u.name = fname;
      u.email = email;
      u.role = role;
      u.group = group;
    }
    editingId = null;
    showToast('User berhasil diperbarui!', 'ok');
  } else {
    if (users.find(x => x.username === uname)) {
      showToast('Username sudah dipakai!', 'err');
      return;
    }

    users.push({
      id: nextId++,
      username: uname,
      name: fname,
      email,
      role,
      group,
      status: 'offline',
      isNew: true
    });

    showToast('User ' + uname + ' berhasil ditambahkan!', 'ok');
  }

  resetForm();
  filterTable();
}

function resetForm() {
  editingId = null;
  openAddForm();
}

/* ================= TOAST ================= */
function showToast(msg, type) {
  const t = document.getElementById('form-toast');
  t.textContent = msg;
  t.className = 'toast ' + (type === 'ok' ? 'toast-ok' : 'toast-del');
  t.style.display = 'block';

  setTimeout(() => {
    t.style.display = 'none';
  }, 3000);
}

function clearToast() {
  document.getElementById('form-toast').style.display = 'none';
}

function openDelete(id) {
  const u = users.find(x => x.id === id);
  if (!u) return;

  deleteTargetId = id;
  document.getElementById('del-uname').textContent = u.username;
  document.getElementById('delete-modal').style.display = 'block';
}

function closeDelete() {
  deleteTargetId = null;
  document.getElementById('delete-modal').style.display = 'none';
}

function confirmDelete() {
  users = users.filter(u => u.id !== deleteTargetId);
  filtered = filtered.filter(u => u.id !== deleteTargetId);

  closeDelete();

  if (editingId === deleteTargetId) {
    editingId = null;
    openAddForm();
  }

  renderTable();
}

/* ================= INIT ================= */
renderTable();
validateForm();