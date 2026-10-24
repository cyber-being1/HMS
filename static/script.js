// ==================== Setup ====================
let token = localStorage.getItem('hms_token');
let role = null, doctorsCache = [];

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); // XSS se bachav
const fmt = d => d.replace('T', ' ').slice(0, 16);
const badge = (t, c) => `<span class="badge ${c}">${esc(t)}</span>`;
const statusBadge = s => badge(s, s === 'completed' ? 'ok' : 'warn');
const calcAge = dob => {
    const b = new Date(dob);
    if (!dob || isNaN(b)) return '-';
    const t = new Date();
    return t.getFullYear() - b.getFullYear() - (t < new Date(t.getFullYear(), b.getMonth(), b.getDate()) ? 1 : 0);
};

// Role ke hisaab se kaun se page / "Add" buttons dikhne chahiye (null = sab)
const PAGES = {
    admin: null,
    doctor: ['dashboard', 'patients', 'doctors', 'appointments', 'departments', 'records', 'beds'],
    patient: ['dashboard', 'appointments', 'doctors', 'records']
};
const CAN_ADD = { admin: null, doctor: ['recordModal'], patient: ['appointmentModal'] };

// ==================== API helper ====================

async function api(path, method = 'GET', body = null) {
    const res = await fetch('/api' + path, {
        method,
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
        body: body ? JSON.stringify(body) : null
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        if (res.status === 401 && token) logout();
        let msg = data.detail || 'Something went wrong';
        if (Array.isArray(msg)) msg = msg.map(e => e.msg.replace('Value error, ', '')).join('\n');
        throw new Error(msg);
    }
    return data;
}

// list ko table/grid me bharta hai
async function fill(id, path, row) {
    try {
        const items = await api(path);
        const el = $(id);
        el.innerHTML = items.map(row).join('') ||
            (el.tagName === 'TBODY' ? '<tr><td colspan="9" class="empty">No data yet</td></tr>' : '<p class="empty">No data yet</p>');
        return items;
    } catch (err) { alert(err.message); }
}

// form submit: POST -> modal band -> message -> list refresh
function onSubmit(formId, path, body, modal, msg, after) {
    $(formId).addEventListener('submit', async e => {
        e.preventDefault();
        try {
            await api(path, 'POST', body());
            $(modal).classList.remove('active');
            e.target.reset();
            alert(msg);
            after();
        } catch (err) { alert(err.message); }
    });
}
const val = id => $(id).value;

// ==================== Navigation, modals, clicks ====================

const LOADERS = {
    dashboard: loadDashboard,
    patients: () => fill('patientsList', '/patients', p => `<tr><td>#${p.id}</td><td>${esc(p.name)}</td><td>${esc(p.phone)}</td><td>${esc(p.blood_group)}</td><td>${calcAge(p.date_of_birth)}</td><td>${esc(p.address)}</td></tr>`),
    doctors: async () => { doctorsCache = await api('/doctors'); renderDoctors(); },
    appointments: () => { fillSelects(); fill('appointmentsList', '/appointments', a => `<tr><td>#${a.id}</td><td>${esc(a.patient_name)}</td><td>${esc(a.doctor_name)}</td><td>${fmt(a.appointment_date)}</td><td>${esc(a.reason)}</td><td>${statusBadge(a.status)}</td></tr>`); },
    departments: () => fill('departmentsList', '/departments', d => `<div class="card"><div class="icon">🏥</div><h3>${esc(d.name)}</h3><p><b>Head:</b> ${esc(d.head)}</p><p><b>Phone:</b> ${esc(d.phone)}</p><p>${esc(d.description)}</p></div>`),
    records: () => fill('recordsList', '/medical-records', r => `<tr><td>#${r.id}</td><td>${esc(r.patient_name)}</td><td>${esc(r.doctor_name)}</td><td>${esc(r.diagnosis)}</td><td>${fmt(r.created_at)}</td></tr>`),
    medicines: () => fill('medicinesList', '/medicines', m => `<tr><td>#${m.id}</td><td>${esc(m.name)}</td><td>${esc(m.manufacturer)}</td><td>₹${m.price}</td><td>${m.stock}</td><td>${esc(m.expiry_date)}</td></tr>`),
    beds: () => fill('bedsList', '/beds', b => `<tr><td>#${b.id}</td><td>${esc(b.room_number)}</td><td>${esc(b.bed_number)}</td><td>${esc(b.department)}</td><td>${badge(b.status, b.status === 'available' ? 'ok' : 'bad')}</td><td>${esc(b.patient_admitted) || 'None'}</td><td><button class="btn-sm" data-bed="${b.id}">${b.status === 'available' ? 'Mark Occupied' : 'Mark Available'}</button></td></tr>`)
};

function openPage(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === name));
    document.querySelectorAll('.menu-item').forEach(m => m.classList.toggle('active', m.dataset.page === name));
    LOADERS[name]();
}

// ek hi click listener: page badalna, modal kholna/band karna, bed toggle
document.addEventListener('click', async e => {
    const t = e.target;
    if (t.dataset.signup !== undefined) { e.preventDefault(); showCard(t.dataset.signup); }
    const nav = t.closest('[data-page]');
    if (nav) { e.preventDefault(); openPage(nav.dataset.page); }
    if (t.dataset.open) $(t.dataset.open).classList.add('active');
    if (t.dataset.close || (t.classList.contains('modal') && t.closest('#appContainer'))) {
        (t.dataset.close ? $(t.dataset.close) : t).classList.remove('active');
    }
    if (t.dataset.bed) {
        try { await api(`/beds/${t.dataset.bed}/status`, 'PUT'); LOADERS.beds(); } catch (err) { alert(err.message); }
    }
    if (t.id === 'logoutBtn') logout();
});

// ==================== Auth ====================

function showCard(which) {
    $('loginModal').classList.toggle('active', which === 'login');
    $('registerModal').classList.toggle('active', which === 'register');
    // card badalne ya logout par password dobara hide kar do
    document.querySelectorAll('[data-showpw]').forEach(cb => { cb.checked = false; $(cb.dataset.showpw).type = 'password'; });
}

document.querySelectorAll('[data-showpw]').forEach(cb =>
    cb.addEventListener('change', () => { $(cb.dataset.showpw).type = cb.checked ? 'text' : 'password'; }));

function setMsg(id, text, ok) { $(id).textContent = text; $(id).classList.toggle('ok', !!ok); }

function logout() {
    token = role = null;
    localStorage.removeItem('hms_token');
    $('appContainer').hidden = true;
    $('loginForm').reset();
    $('registerForm').reset();
    showCard('login');
}

function showApp(user) {
    role = user.role;
    $('appContainer').hidden = false;
    $('loginModal').classList.remove('active');
    $('userDisplay').textContent = 'Welcome, ' + user.username;
    $('currentUser').textContent = user.username;
    $('currentRole').textContent = role;

    // role ke hisaab se menu aur buttons
    const pages = PAGES[role], add = CAN_ADD[role];
    document.querySelectorAll('.menu-item').forEach(m => m.hidden = !!pages && !pages.includes(m.dataset.page));
    document.querySelectorAll('[data-open], [data-need]').forEach(b => b.hidden = !!add && !add.includes(b.dataset.open || b.dataset.need));
    $('appointmentPatient').closest('.form-group').hidden = role === 'patient';   // patient apne hi liye book karta hai

    // date limits: future DOB aur past appointment nahi
    const now = new Date(), pad = n => String(n).padStart(2, '0');
    $('patientDOB').max = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    $('appointmentDateTime').min = `${$('patientDOB').max}T${pad(now.getHours())}:${pad(now.getMinutes())}`;

    fillSelects();
    openPage('dashboard');
}

function passwordLevel(p) {
    const core = p.length >= 8 && /[a-z]/.test(p) && /[A-Z]/.test(p) && /\d/.test(p);
    if (!core) return ['Weak (min 8 chars, 1 capital, 1 small, 1 number)', 'bad', false];
    return /[^A-Za-z0-9]/.test(p) && p.length >= 10 ? ['Strong', 'ok', true] : ['Medium', 'warn', true];
}

$('regPassword').addEventListener('input', e => {
    const p = e.target.value;
    const [text, color] = p ? passwordLevel(p) : ['', ''];
    $('pwText').textContent = text ? 'Password strength: ' + text : '';
    $('pwText').className = 'pw ' + color;
});

$('loginForm').addEventListener('submit', async e => {
    e.preventDefault();
    try {
        const data = await api('/auth/login', 'POST', { username: val('username').trim(), password: val('password'), role: val('role') });
        token = data.token;
        localStorage.setItem('hms_token', token);
        setMsg('loginMsg', '');
        showApp(data);
    } catch (err) { setMsg('loginMsg', err.message); }
});

$('registerForm').addEventListener('submit', async e => {
    e.preventDefault();
    if (!passwordLevel(val('regPassword'))[2]) return setMsg('regMsg', 'Weak password');
    try {
        await api('/auth/register', 'POST', {
            username: val('regUsername').trim(), email: val('regEmail').trim(),
            password: val('regPassword'), date_of_birth: val('regDOB')
        });
        setMsg('regMsg', 'Registered successfully! Please login.', true);
        setTimeout(() => { e.target.reset(); setMsg('regMsg', ''); showCard('login'); }, 1200);
    } catch (err) { setMsg('regMsg', err.message); }
});

// ==================== Dropdowns ====================

async function fillSelects() {
    try {
        const [patients, doctors, depts] = await Promise.all([api('/patients'), api('/doctors'), api('/departments')]);
        doctorsCache = doctors;
        const opts = (list, label, v = x => x.id) => `<option value="">${label}</option>` + list.map(x => `<option value="${esc(v(x))}">${esc(x.name)}</option>`).join('');
        $('appointmentPatient').innerHTML = $('recordPatient').innerHTML = opts(patients, 'Select Patient');
        $('appointmentDoctor').innerHTML = $('recordDoctor').innerHTML = opts(doctors, 'Select Doctor');
        $('departmentFilter').innerHTML = opts(depts, 'All Departments', d => d.name);
        $('doctorDept').innerHTML = opts(depts, 'Select Department', d => d.name);
        $('bedDept').innerHTML = opts(depts, 'Select Department');
        if (role === 'patient' && patients.length === 1) $('appointmentPatient').value = patients[0].id;
    } catch (err) { console.error(err); }
}

// ==================== Dashboard ====================

async function loadDashboard() {
    try {
        if (role !== 'patient') {
            const s = await api('/dashboard/stats');
            $('totalPatients').textContent = s.total_patients;
            $('totalDoctors').textContent = s.total_doctors;
            $('totalAppointments').textContent = s.total_appointments;
            $('availableBeds').textContent = s.available_beds;
        }
        const apts = await api('/appointments');
        $('recentAppointments').querySelector('tbody').innerHTML = apts.slice(-5).reverse().map(a =>
            `<tr><td>${esc(a.patient_name)}</td><td>${esc(a.doctor_name)}</td><td>${fmt(a.appointment_date)}</td><td>${statusBadge(a.status)}</td></tr>`).join('');
    } catch (err) { console.error(err); }
}

// ==================== Doctors ====================

function renderDoctors() {
    const f = val('departmentFilter');
    $('doctorsList').innerHTML = doctorsCache.filter(d => !f || d.department === f).map(d => `
        <div class="card">
            <div class="icon">👨‍⚕️</div>
            <h3>${esc(d.name)}</h3>
            <p><b>Specialization:</b> ${esc(d.specialization)}</p>
            <p><b>Qualification:</b> ${esc(d.qualification)}</p>
            <p><b>Experience:</b> ${d.experience} years</p>
            <p><b>Department:</b> ${esc(d.department)}</p>
            <p class="fee">₹${d.fee}/consultation</p>
        </div>`).join('') || '<p class="empty">No data yet</p>';
}
$('departmentFilter').addEventListener('change', renderDoctors);

// patients page ki search box
$('patientSearch').addEventListener('input', e => {
    const q = e.target.value.toUpperCase();
    document.querySelectorAll('#patientsList tr').forEach(r => r.hidden = !r.textContent.toUpperCase().includes(q));
});

// ==================== Add forms ====================

onSubmit('patientForm', '/patients', () => ({
    name: val('patientName'), email: val('patientEmail'), phone: val('patientPhone'),
    blood_group: val('patientBlood'), date_of_birth: val('patientDOB'), gender: val('patientGender'),
    address: val('patientAddress'), emergency_contact: val('patientEmergency')
}), 'patientModal', 'Patient added successfully!', () => { LOADERS.patients(); fillSelects(); });

onSubmit('doctorForm', '/doctors', () => ({
    name: val('doctorName'), email: val('doctorEmail'), phone: val('doctorPhone'), department: val('doctorDept'),
    specialization: val('doctorSpecialization'), qualification: val('doctorQualification'),
    experience: parseInt(val('doctorExperience')), consultation_fee: parseFloat(val('doctorFee'))
}), 'doctorModal', 'Doctor added successfully!', () => { LOADERS.doctors(); fillSelects(); });

onSubmit('appointmentForm', '/appointments', () => ({
    patient_id: parseInt(val('appointmentPatient')), doctor_id: parseInt(val('appointmentDoctor')),
    appointment_date: val('appointmentDateTime'), reason: val('appointmentReason')
}), 'appointmentModal', 'Appointment booked successfully!', () => LOADERS.appointments());

onSubmit('departmentForm', '/departments', () => ({
    name: val('departmentName'), head: val('departmentHead'),
    phone: val('departmentPhone'), description: val('departmentDesc')
}), 'departmentModal', 'Department added successfully!', () => { LOADERS.departments(); fillSelects(); });

onSubmit('recordForm', '/medical-records', () => ({
    patient_id: parseInt(val('recordPatient')), doctor_id: parseInt(val('recordDoctor')),
    symptoms: val('recordSymptoms'), diagnosis: val('recordDiagnosis'), treatment: val('recordTreatment')
}), 'recordModal', 'Record created!', () => LOADERS.records());

onSubmit('medicineForm', '/medicines', () => ({
    name: val('medicineName'), manufacturer: val('medicineManufacturer'), price: parseFloat(val('medicinePrice')),
    stock: parseInt(val('medicineStock')), expiry_date: val('medicineExpiry')
}), 'medicineModal', 'Medicine added to inventory!', () => LOADERS.medicines());

onSubmit('bedForm', '/beds', () => ({
    department_id: parseInt(val('bedDept')), room_number: val('bedRoom'), bed_number: val('bedNumber')
}), 'bedModal', 'Bed added successfully!', () => LOADERS.beds());

// ==================== Start: token valid ho to seedha app ====================

(async () => {
    if (!token) return showCard('login');
    try { showApp(await api('/auth/me')); } catch { logout(); }
})();