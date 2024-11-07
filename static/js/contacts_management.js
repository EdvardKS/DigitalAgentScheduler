document.addEventListener('DOMContentLoaded', () => {
    // Initialize components
    const viewContactModal = new bootstrap.Modal(document.getElementById('viewContactModal'));
    
    // Pagination settings
    let currentContactPage = 1;
    const itemsPerPage = 10;
    let filteredContacts = [];
    let currentContactFilter = 'all';
    let retryAttempts = 0;
    const maxRetries = 3;
    const retryDelay = 1000;

    // Format phone number for display
    function formatPhoneNumber(phone) {
        if (!phone) return '-';
        return phone.replace(/(\d{3})(\d{3})(\d{3})/, '$1 $2 $3');
    }

    // Get status badge class
    function getStatusBadgeClass(status) {
        const statusClasses = {
            'Nuevo': 'warning',
            'En Proceso': 'info',
            'Completado': 'success'
        };
        return statusClasses[status] || 'secondary';
    }

    // Show alert message
    function showAlert(type, message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show mt-3`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.querySelector('#contacts .card-body').prepend(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }

    // Update pagination
    function updateContactPagination() {
        const totalPages = Math.ceil(filteredContacts.length / itemsPerPage);
        const pagination = document.getElementById('contactPagination');
        pagination.innerHTML = '';

        if (totalPages <= 1) return;

        // Previous button
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${currentContactPage === 1 ? 'disabled' : ''}`;
        prevLi.innerHTML = `<a class="page-link" href="#" data-page="${currentContactPage - 1}">Anterior</a>`;
        pagination.appendChild(prevLi);

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${currentContactPage === i ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link" href="#" data-page="${i}">${i}</a>`;
            pagination.appendChild(li);
        }

        // Next button
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${currentContactPage === totalPages ? 'disabled' : ''}`;
        nextLi.innerHTML = `<a class="page-link" href="#" data-page="${currentContactPage + 1}">Siguiente</a>`;
        pagination.appendChild(nextLi);

        // Add click events
        pagination.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const newPage = parseInt(e.target.dataset.page);
                if (!isNaN(newPage) && newPage !== currentContactPage && newPage > 0 && newPage <= totalPages) {
                    currentContactPage = newPage;
                    displayContacts();
                }
            });
        });
    }

    // Filter contacts
    function filterContacts(contacts, filter) {
        switch(filter) {
            case 'new':
                return contacts.filter(contact => contact.status === 'Nuevo');
            case 'inprocess':
                return contacts.filter(contact => contact.status === 'En Proceso');
            case 'completed':
                return contacts.filter(contact => contact.status === 'Completado');
            default:
                return contacts;
        }
    }

    // Display contacts
    function displayContacts() {
        const start = (currentContactPage - 1) * itemsPerPage;
        const end = start + itemsPerPage;
        const paginatedContacts = filteredContacts.slice(start, end);

        const tbody = document.getElementById('contactsTableBody');
        tbody.innerHTML = paginatedContacts.map(contact => `
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

        // Update pagination
        updateContactPagination();
        
        // Update total records count
        document.getElementById('totalContactRecords').textContent = filteredContacts.length;

        // Add event listeners for view buttons
        document.querySelectorAll('.view-contact').forEach(button => {
            button.addEventListener('click', () => viewContact(button.dataset.id));
        });
    }

    // Load contacts with retry mechanism
    async function loadContacts(retry = true) {
        try {
            const response = await fetch('/api/contacts', {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (response.status === 401) {
                throw new Error('PIN verification required');
            }
            
            const data = await response.json();
            
            if (data.contacts) {
                filteredContacts = filterContacts(data.contacts, currentContactFilter);
                displayContacts();
                updateContactCharts(data.contacts);
                return data.contacts;
            }
            
            retryAttempts = 0;
            return null;
        } catch (error) {
            console.error('Error:', error);
            if (retry && retryAttempts < maxRetries) {
                retryAttempts++;
                showAlert('warning', `Error al cargar contactos. Reintentando (${retryAttempts}/${maxRetries})...`);
                setTimeout(() => loadContacts(), retryDelay * retryAttempts);
            } else {
                showAlert('danger', 'Error al cargar los contactos. Por favor, actualice la página.');
            }
            throw error;
        }
    }

    // View contact details
    function viewContact(id) {
        const contact = filteredContacts.find(c => c.id === parseInt(id));
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

    // Update contact status
    document.getElementById('saveContactChanges').addEventListener('click', async () => {
        const id = document.getElementById('editContactId').value;
        const status = document.getElementById('editContactStatus').value;

        try {
            const response = await fetch(`/api/contacts/${id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ status })
            });

            const data = await response.json();

            if (data.message) {
                viewContactModal.hide();
                await loadContacts(false);
                showAlert('success', 'Estado del contacto actualizado correctamente');
            } else {
                throw new Error(data.error || 'Error al actualizar el estado del contacto');
            }
        } catch (error) {
            console.error('Error:', error);
            showAlert('danger', error.message || 'Error al actualizar el estado del contacto. Por favor, intente de nuevo.');
        }
    });

    // Update contact charts
    function updateContactCharts(contacts) {
        try {
            // Update Contact Status Chart
            const statusChart = Chart.getChart('contactStatusChart');
            if (statusChart) {
                const statusCounts = contacts.reduce((acc, contact) => {
                    acc[contact.status] = (acc[contact.status] || 0) + 1;
                    return acc;
                }, {});

                statusChart.data.datasets[0].data = [
                    statusCounts['Nuevo'] || 0,
                    statusCounts['En Proceso'] || 0,
                    statusCounts['Completado'] || 0
                ];
                statusChart.update();
            }

            // Update Contact Timeline Chart
            const timelineChart = Chart.getChart('contactTimelineChart');
            if (timelineChart) {
                const dateGroups = contacts.reduce((acc, contact) => {
                    const date = contact.created_at.split(' ')[0];
                    acc[date] = (acc[date] || 0) + 1;
                    return acc;
                }, {});

                const sortedDates = Object.keys(dateGroups).sort();
                timelineChart.data.labels = sortedDates;
                timelineChart.data.datasets[0].data = sortedDates.map(date => dateGroups[date]);
                timelineChart.update();
            }
        } catch (error) {
            console.error('Error updating contact charts:', error);
            showAlert('warning', 'Error al actualizar los gráficos de contactos');
        }
    }

    // Filter dropdown handler
    document.querySelectorAll('[data-contact-filter]').forEach(filterLink => {
        filterLink.addEventListener('click', (e) => {
            e.preventDefault();
            currentContactFilter = e.target.dataset.contactFilter;
            currentContactPage = 1;
            loadContacts();
        });
    });

    // Refresh contacts handler
    document.getElementById('refreshContacts').addEventListener('click', () => loadContacts(false));

    // Initialize contact charts
    function initializeContactCharts() {
        // Contact Status Chart
        new Chart(document.getElementById('contactStatusChart').getContext('2d'), {
            type: 'pie',
            data: {
                labels: ['Nuevo', 'En Proceso', 'Completado'],
                datasets: [{
                    data: [0, 0, 0],
                    backgroundColor: ['#ffc107', '#17a2b8', '#28a745']
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
        new Chart(document.getElementById('contactTimelineChart').getContext('2d'), {
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

    // Initialize on load
    if (sessionStorage.getItem('pinVerified')) {
        initializeContactCharts();
        loadContacts();
    }
});
