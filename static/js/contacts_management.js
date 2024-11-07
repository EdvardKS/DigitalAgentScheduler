document.addEventListener('DOMContentLoaded', () => {
    // Get contacts table elements
    const contactsTableBody = document.getElementById('contactsTableBody');
    const totalContactRecords = document.getElementById('totalContactRecords');
    const contactPagination = document.getElementById('contactPagination');
    const refreshContactsBtn = document.getElementById('refreshContacts');
    const viewContactModal = new bootstrap.Modal(document.getElementById('viewContactModal'));

    // Pagination settings
    let currentContactPage = 1;
    const itemsPerPage = 10;
    let filteredContacts = [];
    let currentContactFilter = 'all';

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
        return `bg-${statusClasses[status] || 'secondary'}`;
    }

    // Update pagination
    function updateContactPagination() {
        const totalPages = Math.ceil(filteredContacts.length / itemsPerPage);
        contactPagination.innerHTML = '';

        if (totalPages <= 1) return;

        // Previous button
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${currentContactPage === 1 ? 'disabled' : ''}`;
        prevLi.innerHTML = `<a class="page-link" href="#" data-page="${currentContactPage - 1}">Anterior</a>`;
        contactPagination.appendChild(prevLi);

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${currentContactPage === i ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link" href="#" data-page="${i}">${i}</a>`;
            contactPagination.appendChild(li);
        }

        // Next button
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${currentContactPage === totalPages ? 'disabled' : ''}`;
        nextLi.innerHTML = `<a class="page-link" href="#" data-page="${currentContactPage + 1}">Siguiente</a>`;
        contactPagination.appendChild(nextLi);

        // Add click events
        contactPagination.querySelectorAll('.page-link').forEach(link => {
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

    // Display contacts with pagination
    function displayContacts() {
        const start = (currentContactPage - 1) * itemsPerPage;
        const end = start + itemsPerPage;
        const paginatedContacts = filteredContacts.slice(start, end);

        contactsTableBody.innerHTML = paginatedContacts.map(contact => `
            <tr>
                <td>${new Date(contact.created_at).toLocaleDateString('es-ES')}</td>
                <td>${contact.name}</td>
                <td>${contact.email}</td>
                <td>${formatPhoneNumber(contact.phone)}</td>
                <td>${contact.city || '-'}</td>
                <td>
                    <span class="badge ${getStatusBadgeClass(contact.status)}">
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
        totalContactRecords.textContent = filteredContacts.length;

        // Add event listeners for view buttons
        document.querySelectorAll('.view-contact').forEach(button => {
            button.addEventListener('click', () => viewContact(button.dataset.id));
        });
    }

    // View contact details
    function viewContact(id) {
        const contact = filteredContacts.find(c => c.id === parseInt(id));
        if (!contact) return;

        // Populate modal fields
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

    // Load contacts
    function loadContacts() {
        fetch('/api/contacts', {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (response.status === 401) {
                window.location.reload();
                throw new Error('PIN verification required');
            }
            return response.json();
        })
        .then(data => {
            if (data.contacts) {
                filteredContacts = filterContacts(data.contacts, currentContactFilter);
                displayContacts();
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('danger', 'Error al cargar los contactos. Por favor, intente de nuevo.');
        });
    }

    // Show alert message
    function showAlert(type, message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show mt-3`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.querySelector('.card-body').prepend(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }

    // Save contact status changes
    document.getElementById('saveContactChanges').addEventListener('click', () => {
        const id = document.getElementById('editContactId').value;
        const status = document.getElementById('editContactStatus').value;

        fetch(`/api/contacts/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ status })
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                viewContactModal.hide();
                loadContacts();
                showAlert('success', 'Estado del contacto actualizado correctamente');
            } else {
                throw new Error(data.error || 'Error al actualizar el estado del contacto');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('danger', error.message || 'Error al actualizar el estado del contacto. Por favor, intente de nuevo.');
        });
    });

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
    refreshContactsBtn.addEventListener('click', loadContacts);

    // Initial load
    loadContacts();
});
