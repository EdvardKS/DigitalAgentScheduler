document.addEventListener('DOMContentLoaded', () => {
    // Initialize charts and setup PIN verification
    const pinModal = new bootstrap.Modal(document.getElementById('pinModal'));
    const dashboardContent = document.getElementById('dashboardContent');
    const editModal = new bootstrap.Modal(document.getElementById('editAppointmentModal'));
    const viewContactModal = new bootstrap.Modal(document.getElementById('viewContactModal'));

    // Pagination settings
    let currentPage = 1;
    const itemsPerPage = 10;
    let filteredAppointments = [];
    let currentFilter = 'all';

    // Show PIN modal on page load
    pinModal.show();

    // Format phone number for display
    function formatPhoneNumber(phone) {
        if (!phone) return '-';
        return phone.replace(/(\d{3})(\d{3})(\d{3})/, '$1 $2 $3');
    }

    // PIN verification
    document.getElementById('verifyPin').addEventListener('click', () => {
        const enteredPin = document.getElementById('pinInput').value;
        
        fetch('/api/verify-pin', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ pin: enteredPin }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                pinModal.hide();
                dashboardContent.style.display = 'block';
                loadAppointments();
                loadContacts();
                initializeCharts();
            } else {
                document.getElementById('pinInput').classList.add('is-invalid');
            }
        });
    });

    // Initialize Charts
    function initializeCharts() {
        // Services Distribution Chart
        const servicesCtx = document.getElementById('servicesChart').getContext('2d');
        new Chart(servicesCtx, {
            type: 'pie',
            data: {
                labels: ['Inteligencia Artificial', 'Ventas Digitales', 'Estrategia y Rendimiento'],
                datasets: [{
                    data: [0, 0, 0],
                    backgroundColor: [
                        '#d8001d',
                        '#ff6384',
                        '#ff9f40'
                    ]
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });

        // Timeline Chart
        const timelineCtx = document.getElementById('timelineChart').getContext('2d');
        new Chart(timelineCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Citas por día',
                    data: [],
                    borderColor: '#d8001d',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });

        // Contact Status Chart
        const contactStatusCtx = document.getElementById('contactStatusChart').getContext('2d');
        new Chart(contactStatusCtx, {
            type: 'pie',
            data: {
                labels: ['Nuevo', 'En Proceso', 'Completado'],
                datasets: [{
                    data: [0, 0, 0],
                    backgroundColor: [
                        '#ffc107',
                        '#17a2b8',
                        '#28a745'
                    ]
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });

        // Contact Timeline Chart
        const contactTimelineCtx = document.getElementById('contactTimelineChart').getContext('2d');
        new Chart(contactTimelineCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Consultas por día',
                    data: [],
                    borderColor: '#d8001d',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    }

    // Update Charts
    function updateCharts(appointments, contacts) {
        // Update Services Distribution
        const serviceCounts = {
            'Inteligencia Artificial': 0,
            'Ventas Digitales': 0,
            'Estrategia y Rendimiento': 0
        };

        appointments.forEach(apt => {
            if (serviceCounts.hasOwnProperty(apt.service)) {
                serviceCounts[apt.service]++;
            }
        });

        const servicesChart = Chart.getChart('servicesChart');
        servicesChart.data.datasets[0].data = Object.values(serviceCounts);
        servicesChart.update();

        // Update Timeline
        const dateGroups = {};
        appointments.forEach(apt => {
            if (!dateGroups[apt.date]) {
                dateGroups[apt.date] = 0;
            }
            dateGroups[apt.date]++;
        });

        const sortedDates = Object.keys(dateGroups).sort();
        const timelineChart = Chart.getChart('timelineChart');
        timelineChart.data.labels = sortedDates;
        timelineChart.data.datasets[0].data = sortedDates.map(date => dateGroups[date]);
        timelineChart.update();

        // Update Contact Status Chart
        const statusCounts = {
            'Nuevo': 0,
            'En Proceso': 0,
            'Completado': 0
        };

        contacts.forEach(contact => {
            if (statusCounts.hasOwnProperty(contact.status)) {
                statusCounts[contact.status]++;
            }
        });

        const contactStatusChart = Chart.getChart('contactStatusChart');
        contactStatusChart.data.datasets[0].data = Object.values(statusCounts);
        contactStatusChart.update();

        // Update Contact Timeline
        const contactDateGroups = {};
        contacts.forEach(contact => {
            const date = contact.created_at.split(' ')[0];
            if (!contactDateGroups[date]) {
                contactDateGroups[date] = 0;
            }
            contactDateGroups[date]++;
        });

        const sortedContactDates = Object.keys(contactDateGroups).sort();
        const contactTimelineChart = Chart.getChart('contactTimelineChart');
        contactTimelineChart.data.labels = sortedContactDates;
        contactTimelineChart.data.datasets[0].data = sortedContactDates.map(date => contactDateGroups[date]);
        contactTimelineChart.update();
    }

    // Load appointments
    function loadAppointments() {
        fetch('/api/appointments')
            .then(response => {
                if (response.status === 401) {
                    pinModal.show();
                    throw new Error('PIN verification required');
                }
                return response.json();
            })
            .then(data => {
                if (data.appointments) {
                    filteredAppointments = filterAppointments(data.appointments, currentFilter);
                    displayAppointments();
                    loadContacts().then(contacts => {
                        updateCharts(data.appointments, contacts);
                        updateSummaryCards(data.appointments, contacts);
                    });
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error loading appointments. Please try again.');
            });
    }

    // Load contacts
    function loadContacts() {
        return fetch('/api/contacts')
            .then(response => {
                if (response.status === 401) {
                    pinModal.show();
                    throw new Error('PIN verification required');
                }
                return response.json();
            })
            .then(data => {
                if (data.contacts) {
                    displayContacts(data.contacts);
                    return data.contacts;
                }
                return [];
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error loading contacts. Please try again.');
                return [];
            });
    }

    // Update summary cards
    function updateSummaryCards(appointments, contacts) {
        const today = new Date().toISOString().split('T')[0];
        
        document.getElementById('totalAppointments').textContent = appointments.length;
        document.getElementById('todayAppointments').textContent = 
            appointments.filter(apt => apt.date === today).length;
        document.getElementById('upcomingAppointments').textContent = 
            appointments.filter(apt => apt.date > today).length;
        document.getElementById('newContacts').textContent = 
            contacts.filter(contact => contact.status === 'Nuevo').length;
    }

    // Display contacts
    function displayContacts(contacts) {
        const tbody = document.getElementById('contactsTableBody');
        tbody.innerHTML = contacts.map(contact => `
            <tr>
                <td>${new Date(contact.created_at).toLocaleDateString('es-ES')}</td>
                <td>${contact.name}</td>
                <td>${contact.email}</td>
                <td>${formatPhoneNumber(contact.phone)}</td>
                <td>${contact.city || '-'}</td>
                <td>
                    <span class="badge bg-${getStatusBadgeClass(contact.status)}">
                        ${contact.status}
                    </span>
                </td>
                <td>
                    <button class="btn btn-sm btn-outline-danger view-contact" data-id="${contact.id}">
                        <i data-feather="eye"></i>
                    </button>
                </td>
            </tr>
        `).join('');

        // Update feather icons
        feather.replace();

        // Add event listeners for view buttons
        document.querySelectorAll('.view-contact').forEach(button => {
            button.addEventListener('click', () => viewContact(button.dataset.id));
        });
    }

    // View contact details
    function viewContact(id) {
        const contact = contacts.find(c => c.id === parseInt(id));
        if (!contact) return;

        document.getElementById('editContactId').value = id;
        document.getElementById('viewContactName').value = contact.name;
        document.getElementById('viewContactEmail').value = contact.email;
        document.getElementById('viewContactPhone').value = contact.phone || '';
        document.getElementById('viewContactPostalCode').value = contact.postal_code || '';
        document.getElementById('viewContactCity').value = contact.city || '';
        document.getElementById('viewContactProvince').value = contact.province || '';
        document.getElementById('viewContactInquiry').value = contact.inquiry || '';
        document.getElementById('editContactStatus').value = contact.status;

        viewContactModal.show();
    }

    // Save contact changes
    document.getElementById('saveContactChanges').addEventListener('click', () => {
        const id = document.getElementById('editContactId').value;
        const status = document.getElementById('editContactStatus').value;

        fetch(`/api/contacts/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ status })
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                viewContactModal.hide();
                loadContacts();
            } else {
                alert(data.error || 'Error updating contact status');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error updating contact status. Please try again.');
        });
    });

    // Handle Enter key in PIN input
    document.getElementById('pinInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('verifyPin').click();
        }
    });

    // Refresh buttons
    document.getElementById('refreshAppointments').addEventListener('click', loadAppointments);
    document.getElementById('refreshContacts').addEventListener('click', loadContacts);
});
