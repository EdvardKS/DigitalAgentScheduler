document.addEventListener('DOMContentLoaded', () => {
    // Initialize components
    const pinModal = new bootstrap.Modal(document.getElementById('pinModal'), {
        backdrop: 'static',
        keyboard: false
    });
    const dashboardContent = document.getElementById('dashboardContent');
    const pinInput = document.getElementById('pinInput');
    const pinError = document.getElementById('pinError');
    const editModal = new bootstrap.Modal(document.getElementById('editAppointmentModal'));
    
    // Pagination settings
    let currentPage = 1;
    const itemsPerPage = 10;
    let filteredAppointments = [];
    let currentFilter = 'all';
    let retryAttempts = 0;
    const maxRetries = 3;
    const retryDelay = 1000;

    // Show PIN modal if needed
    if (document.getElementById('pinModal').dataset.bsShow === 'true') {
        pinModal.show();
    }

    // Handle PIN verification
    document.getElementById('verifyPin').addEventListener('click', verifyPin);
    pinInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            verifyPin();
        }
    });

    // Format phone number for display
    function formatPhoneNumber(phone) {
        if (!phone) return '-';
        return phone.replace(/(\d{3})(\d{3})(\d{3})/, '$1 $2 $3');
    }

    // Show alert message
    function showAlert(type, message, container = '.card-body') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show mt-3`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.querySelector(container).prepend(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }

    // PIN verification function with retry
    async function verifyPin() {
        const enteredPin = pinInput.value;
        pinInput.classList.remove('is-invalid');
        pinError.classList.add('d-none');
        
        try {
            const response = await fetch('/api/verify-pin', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ pin: enteredPin }),
            });
            
            const data = await response.json();
            
            if (data.success) {
                pinModal.hide();
                dashboardContent.style.display = 'block';
                sessionStorage.setItem('pinVerified', 'true');
                await loadData();
            } else {
                pinInput.classList.add('is-invalid');
                pinError.classList.remove('d-none');
                pinInput.value = '';
                pinInput.focus();
            }
        } catch (error) {
            console.error('Error:', error);
            pinError.textContent = 'Error de conexión. Por favor, intente de nuevo.';
            pinError.classList.remove('d-none');
        }
    }

    // Load all data with retry mechanism
    async function loadData(retry = true) {
        try {
            const [appointmentsData, contactsData] = await Promise.all([
                loadAppointments(),
                loadContacts()
            ]);
            
            if (appointmentsData && contactsData) {
                updateCharts(appointmentsData, contactsData);
                updateSummaryCards(appointmentsData, contactsData);
            }
            
            retryAttempts = 0;
        } catch (error) {
            console.error('Error loading data:', error);
            if (retry && retryAttempts < maxRetries) {
                retryAttempts++;
                showAlert('warning', `Error al cargar datos. Reintentando (${retryAttempts}/${maxRetries})...`);
                setTimeout(() => loadData(), retryDelay * retryAttempts);
            } else {
                showAlert('danger', 'Error al cargar los datos. Por favor, actualice la página.');
            }
        }
    }

    // Load appointments
    async function loadAppointments() {
        try {
            const response = await fetch('/api/appointments');
            if (response.status === 401) {
                pinModal.show();
                throw new Error('PIN verification required');
            }
            const data = await response.json();
            if (data.appointments) {
                filteredAppointments = filterAppointments(data.appointments, currentFilter);
                displayAppointments();
                return data.appointments;
            }
            return null;
        } catch (error) {
            console.error('Error:', error);
            showAlert('danger', 'Error al cargar las citas. Por favor, intente de nuevo.');
            throw error;
        }
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

    // Update pagination
    function updatePagination() {
        const totalPages = Math.ceil(filteredAppointments.length / itemsPerPage);
        const pagination = document.getElementById('pagination');
        pagination.innerHTML = '';

        if (totalPages <= 1) return;

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

    // Display appointments
    function displayAppointments() {
        const start = (currentPage - 1) * itemsPerPage;
        const end = start + itemsPerPage;
        const paginatedAppointments = filteredAppointments.slice(start, end);
        
        const tbody = document.getElementById('appointmentsTableBody');
        tbody.innerHTML = paginatedAppointments.map(apt => `
            <tr>
                <td>${new Date(apt.date).toLocaleDateString('es-ES')}</td>
                <td>${apt.time}</td>
                <td>${apt.name}</td>
                <td>${apt.email}</td>
                <td>${formatPhoneNumber(apt.phone)}</td>
                <td>${apt.service}</td>
                <td>
                    <span class="badge bg-${getStatusBadgeClass(apt.status)}">
                        ${apt.status}
                    </span>
                </td>
                <td>
                    <button class="btn btn-sm btn-outline-danger edit-appointment" data-id="${apt.id}">
                        <i data-feather="edit-2"></i>
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

        // Add event listeners for edit buttons
        document.querySelectorAll('.edit-appointment').forEach(button => {
            button.addEventListener('click', () => editAppointment(button.dataset.id));
        });
    }

    // Get status badge class
    function getStatusBadgeClass(status) {
        const statusClasses = {
            'Pendiente': 'warning',
            'Confirmado': 'success',
            'Cancelado': 'danger',
            'Completado': 'info'
        };
        return statusClasses[status] || 'secondary';
    }

    // Initialize Charts
    function initializeCharts() {
        const charts = {
            services: {
                ctx: document.getElementById('servicesChart').getContext('2d'),
                config: {
                    type: 'pie',
                    data: {
                        labels: ['Inteligencia Artificial', 'Ventas Digitales', 'Estrategia y Rendimiento'],
                        datasets: [{
                            data: [0, 0, 0],
                            backgroundColor: ['#d8001d', '#ff6384', '#ff9f40']
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
                }
            },
            timeline: {
                ctx: document.getElementById('timelineChart').getContext('2d'),
                config: {
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
                }
            }
        };

        // Create charts
        Object.keys(charts).forEach(key => {
            new Chart(charts[key].ctx, charts[key].config);
        });
    }

    // Update Charts
    function updateCharts(appointments, contacts) {
        try {
            // Update Services Distribution
            const servicesChart = Chart.getChart('servicesChart');
            if (servicesChart) {
                const serviceCounts = appointments.reduce((acc, apt) => {
                    acc[apt.service] = (acc[apt.service] || 0) + 1;
                    return acc;
                }, {});

                servicesChart.data.datasets[0].data = [
                    serviceCounts['Inteligencia Artificial'] || 0,
                    serviceCounts['Ventas Digitales'] || 0,
                    serviceCounts['Estrategia y Rendimiento'] || 0
                ];
                servicesChart.update();
            }

            // Update Timeline
            const timelineChart = Chart.getChart('timelineChart');
            if (timelineChart) {
                const dateGroups = appointments.reduce((acc, apt) => {
                    acc[apt.date] = (acc[apt.date] || 0) + 1;
                    return acc;
                }, {});

                const sortedDates = Object.keys(dateGroups).sort();
                timelineChart.data.labels = sortedDates;
                timelineChart.data.datasets[0].data = sortedDates.map(date => dateGroups[date]);
                timelineChart.update();
            }
        } catch (error) {
            console.error('Error updating charts:', error);
            showAlert('warning', 'Error al actualizar los gráficos');
        }
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

    // Filter dropdown handler
    document.querySelectorAll('[data-filter]').forEach(filterLink => {
        filterLink.addEventListener('click', (e) => {
            e.preventDefault();
            currentFilter = e.target.dataset.filter;
            currentPage = 1;
            loadAppointments();
        });
    });

    // Refresh button handler
    document.getElementById('refreshAppointments').addEventListener('click', () => loadData(false));

    // Initialize on load
    if (sessionStorage.getItem('pinVerified')) {
        dashboardContent.style.display = 'block';
        initializeCharts();
        loadData();
    } else {
        pinModal.show();
    }
});
