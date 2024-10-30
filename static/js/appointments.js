document.addEventListener('DOMContentLoaded', function() {
    const calendarEl = document.getElementById('calendar');
    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek'
        }
    });
    calendar.render();

    const form = document.getElementById('appointmentForm');
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const appointmentData = {
            name: document.getElementById('name').value,
            email: document.getElementById('email').value,
            date: document.getElementById('date').value,
            time: document.getElementById('time').value,
            service: document.getElementById('service').value
        };

        try {
            const response = await fetch('/api/appointments', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(appointmentData)
            });

            if (response.ok) {
                alert('Appointment booked successfully!');
                form.reset();
                calendar.refetchEvents();
            } else {
                alert('Error booking appointment');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error booking appointment');
        }
    });
});
