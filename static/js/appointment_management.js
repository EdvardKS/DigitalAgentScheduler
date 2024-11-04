document.addEventListener('DOMContentLoaded', () => {
    // Check if we're on the correct page
    if (!window.location.pathname.includes('/citas')) {
        window.location.href = '/citas';
        return;
    }

    const pinModal = new bootstrap.Modal(document.getElementById('pinModal'));
    const dashboardContent = document.getElementById('dashboardContent');
    const editModal = new bootstrap.Modal(document.getElementById('editAppointmentModal'));

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
            } else {
                document.getElementById('pinInput').classList.add('is-invalid');
            }
        });
    });

    // Load appointments
    function loadAppointments() {
        fetch('/api/appointments')
            .then(response => {
                if (response.status === 401) {
                    pinModal.show();
                    throw new Error('Se requiere verificación PIN');
                }
                return response.json();
            })
            .then(data => {
                if (data.appointments) {
                    updateDashboard(data.appointments);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error al cargar las citas. Por favor, intente nuevamente.');
            });
    }

    // Update dashboard with appointments data
    function updateDashboard(appointments) {
        const today = new Date().toISOString().split('T')[0];
        
        // Update summary cards
        document.getElementById('totalAppointments').textContent = appointments.length;
        document.getElementById('todayAppointments').textContent = 
            appointments.filter(apt => apt.date === today).length;
        document.getElementById('upcomingAppointments').textContent = 
            appointments.filter(apt => apt.date > today).length;

        // Update appointments table
        const tbody = document.getElementById('appointmentsTableBody');
        tbody.innerHTML = appointments.map(appointment => `
            <tr>
                <td>${appointment.date}</td>
                <td>${appointment.time}</td>
                <td>${appointment.name}</td>
                <td>${appointment.email}</td>
                <td>${appointment.service}</td>
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

        // Initialize Feather icons
        feather.replace();

        // Add event listeners for edit and delete buttons
        document.querySelectorAll('.edit-appointment').forEach(button => {
            button.addEventListener('click', () => editAppointment(button.dataset.id));
        });

        document.querySelectorAll('.delete-appointment').forEach(button => {
            button.addEventListener('click', () => deleteAppointment(button.dataset.id));
        });
    }

    // Edit appointment
    function editAppointment(id) {
        const appointment = document.querySelector(`[data-id="${id}"]`).closest('tr');
        const cells = appointment.getElementsByTagName('td');

        document.getElementById('editAppointmentId').value = id;
        document.getElementById('editDate').value = cells[0].textContent;
        document.getElementById('editTime').value = cells[1].textContent;
        document.getElementById('editName').value = cells[2].textContent;
        document.getElementById('editEmail').value = cells[3].textContent;
        document.getElementById('editService').value = cells[4].textContent;

        editModal.show();
    }

    // Save appointment changes
    document.getElementById('saveAppointmentChanges').addEventListener('click', () => {
        const id = document.getElementById('editAppointmentId').value;
        const appointmentData = {
            date: document.getElementById('editDate').value,
            time: document.getElementById('editTime').value,
            name: document.getElementById('editName').value,
            email: document.getElementById('editEmail').value,
            service: document.getElementById('editService').value
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
                alert(data.error || 'Error al actualizar la cita');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error al actualizar la cita. Por favor, intente nuevamente.');
        });
    });

    // Delete appointment
    function deleteAppointment(id) {
        if (confirm('¿Está seguro de que desea eliminar esta cita?')) {
            fetch(`/api/appointments/${id}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                if (data.message) {
                    loadAppointments();
                } else {
                    alert(data.error || 'Error al eliminar la cita');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error al eliminar la cita. Por favor, intente nuevamente.');
            });
        }
    }

    // Handle Enter key in PIN input
    document.getElementById('pinInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('verifyPin').click();
        }
    });

    // Refresh appointments
    document.getElementById('refreshAppointments').addEventListener('click', loadAppointments);
});