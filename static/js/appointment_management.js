document.addEventListener('DOMContentLoaded', () => {
    const pinModal = new bootstrap.Modal(document.getElementById('pinModal'));
    const dashboardContent = document.getElementById('dashboardContent');
    const editModal = new bootstrap.Modal(document.getElementById('editAppointmentModal'));

    // Pagination settings
    let currentPage = 1;
    const itemsPerPage = 10;
    let filteredAppointments = [];
    let currentFilter = 'all';

    // Show PIN modal on page load
    pinModal.show();

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

        // Appointments Timeline Chart
        const timelineCtx = document.getElementById('appointmentsTimeline').getContext('2d');
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
    }

    // Update Charts
    function updateCharts(appointments) {
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
        const timelineChart = Chart.getChart('appointmentsTimeline');
        timelineChart.data.labels = sortedDates;
        timelineChart.data.datasets[0].data = sortedDates.map(date => dateGroups[date]);
        timelineChart.update();
    }

    // Filter appointments
    function filterAppointments(appointments, filter) {
        const today = new Date().toISOString().split('T')[0];
        
        switch(filter) {
            case 'today':
                return appointments.filter(apt => apt.date === today);
            case 'upcoming':
                return appointments.filter(apt => apt.date > today);
            case 'past':
                return appointments.filter(apt => apt.date < today);
            default:
                return appointments;
        }
    }

    // Pagination
    function updatePagination() {
        const totalPages = Math.ceil(filteredAppointments.length / itemsPerPage);
        const pagination = document.getElementById('pagination');
        pagination.innerHTML = '';

        // Previous button
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
        prevLi.innerHTML = `<a class="page-link" href="#" data-page="${currentPage - 1}">Anterior</a>`;
        pagination.appendChild(prevLi);

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${currentPage === i ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link" href="#" data-page="${i}">${i}</a>`;
            pagination.appendChild(li);
        }

        // Next button
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
        nextLi.innerHTML = `<a class="page-link" href="#" data-page="${currentPage + 1}">Siguiente</a>`;
        pagination.appendChild(nextLi);

        // Add click events
        pagination.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const newPage = parseInt(e.target.dataset.page);
                if (!isNaN(newPage) && newPage !== currentPage && newPage > 0 && newPage <= totalPages) {
                    currentPage = newPage;
                    displayAppointments();
                }
            });
        });
    }

    // Display appointments with pagination
    function displayAppointments() {
        const tbody = document.getElementById('appointmentsTableBody');
        const start = (currentPage - 1) * itemsPerPage;
        const end = start + itemsPerPage;
        const paginatedAppointments = filteredAppointments.slice(start, end);

        tbody.innerHTML = paginatedAppointments.map(appointment => `
            <tr>
                <td>${appointment.date}</td>
                <td>${appointment.time}</td>
                <td>${appointment.name}</td>
                <td>${appointment.email}</td>
                <td>${appointment.phone || '-'}</td>
                <td>${appointment.service}</td>
                <td>
                    <span class="badge bg-${getStatusBadgeClass(appointment.status)}">
                        ${appointment.status || 'Pendiente'}
                    </span>
                </td>
                <td>
                    <button class="btn btn-sm btn-outline-danger edit-appointment" data-id="${appointment.id}">
                        <i data-feather="edit-2"></i>
                    </button>
                    <button class="btn btn-sm btn-danger delete-appointment" data-id="${appointment.id}">
                        <i data-feather="trash-2"></i>
                    </button>
                </td>
            </tr>
        `).join('');

        // Update feather icons
        feather.replace();

        // Update pagination
        updatePagination();
        
        // Update total records count
        document.getElementById('totalRecords').textContent = filteredAppointments.length;

        // Add event listeners for edit and delete buttons
        document.querySelectorAll('.edit-appointment').forEach(button => {
            button.addEventListener('click', () => editAppointment(button.dataset.id));
        });

        document.querySelectorAll('.delete-appointment').forEach(button => {
            button.addEventListener('click', () => deleteAppointment(button.dataset.id));
        });
    }

    function getStatusBadgeClass(status) {
        const statusClasses = {
            'Pendiente': 'warning',
            'Confirmada': 'success',
            'Cancelada': 'danger',
            'Completada': 'info'
        };
        return statusClasses[status] || 'secondary';
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
                    updateCharts(data.appointments);
                    updateSummaryCards(data.appointments);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error loading appointments. Please try again.');
            });
    }

    // Update summary cards
    function updateSummaryCards(appointments) {
        const today = new Date().toISOString().split('T')[0];
        
        document.getElementById('totalAppointments').textContent = appointments.length;
        document.getElementById('todayAppointments').textContent = 
            appointments.filter(apt => apt.date === today).length;
        document.getElementById('upcomingAppointments').textContent = 
            appointments.filter(apt => apt.date > today).length;
    }

    // Edit appointment
    function editAppointment(id) {
        const appointment = filteredAppointments.find(apt => apt.id === parseInt(id));
        if (!appointment) return;

        document.getElementById('editAppointmentId').value = id;
        document.getElementById('editName').value = appointment.name;
        document.getElementById('editEmail').value = appointment.email;
        document.getElementById('editPhone').value = appointment.phone || '';
        document.getElementById('editDate').value = appointment.date;
        document.getElementById('editTime').value = appointment.time;
        document.getElementById('editService').value = appointment.service;
        document.getElementById('editStatus').value = appointment.status || 'Pendiente';

        editModal.show();
    }

    // Save appointment changes
    document.getElementById('saveAppointmentChanges').addEventListener('click', () => {
        const id = document.getElementById('editAppointmentId').value;
        const appointmentData = {
            name: document.getElementById('editName').value,
            email: document.getElementById('editEmail').value,
            phone: document.getElementById('editPhone').value,
            date: document.getElementById('editDate').value,
            time: document.getElementById('editTime').value,
            service: document.getElementById('editService').value,
            status: document.getElementById('editStatus').value
        };

        fetch(`/api/appointments/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(appointmentData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                editModal.hide();
                loadAppointments();
            } else {
                alert(data.error || 'Error updating appointment');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error updating appointment. Please try again.');
        });
    });

    // Delete appointment
    function deleteAppointment(id) {
        if (confirm('Are you sure you want to delete this appointment?')) {
            fetch(`/api/appointments/${id}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                if (data.message) {
                    loadAppointments();
                } else {
                    alert(data.error || 'Error deleting appointment');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error deleting appointment. Please try again.');
            });
        }
    }

    // Filter dropdown handler
    document.querySelectorAll('[data-filter]').forEach(filterLink => {
        filterLink.addEventListener('click', (e) => {
            e.preventDefault();
            currentFilter = e.target.dataset.filter;
            currentPage = 1;
            loadAppointments();
        });
    });

    // Handle Enter key in PIN input
    document.getElementById('pinInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('verifyPin').click();
        }
    });

    // Refresh appointments
    document.getElementById('refreshAppointments').addEventListener('click', loadAppointments);
});
