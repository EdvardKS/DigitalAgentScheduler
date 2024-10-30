document.addEventListener('DOMContentLoaded', () => {
    const pinModal = new bootstrap.Modal(document.getElementById('pinModal'));
    const dashboardContent = document.getElementById('dashboardContent');

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
                initializeDashboard();
            } else {
                document.getElementById('pinInput').classList.add('is-invalid');
            }
        });
    });

    function initializeDashboard() {
        fetchAnalytics();
        initializeCharts();
        // Refresh data every 5 minutes
        setInterval(fetchAnalytics, 300000);
    }

    function fetchAnalytics() {
        Promise.all([
            fetch('/api/analytics/appointments').then(r => r.json()),
            fetch('/api/analytics/inquiries').then(r => r.json())
        ])
        .then(([appointmentData, inquiryData]) => {
            updateDashboard(appointmentData, inquiryData);
        });
    }

    function updateDashboard(appointmentData, inquiryData) {
        // Update summary cards
        document.getElementById('totalAppointments').textContent = appointmentData.total;
        document.getElementById('monthlyAppointments').textContent = appointmentData.monthly;
        document.getElementById('totalInquiries').textContent = inquiryData.total;
        
        // Update recent appointments table
        const tbody = document.getElementById('recentAppointments');
        tbody.innerHTML = appointmentData.recent.map(apt => `
            <tr>
                <td>${apt.date}</td>
                <td>${apt.time}</td>
                <td>${apt.service}</td>
                <td><span class="badge bg-success">Confirmed</span></td>
            </tr>
        `).join('');

        // Update chatbot metrics
        document.getElementById('avgResponseTime').textContent = `${inquiryData.avgResponseTime} ms`;
        document.getElementById('successRate').textContent = `${inquiryData.successRate}%`;

        // Update charts
        updateCharts(appointmentData, inquiryData);
    }

    let serviceChart, timelineChart, inquiryChart;

    function initializeCharts() {
        // Services Chart
        const serviceCtx = document.getElementById('serviceChart').getContext('2d');
        serviceChart = new Chart(serviceCtx, {
            type: 'pie',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    backgroundColor: [
                        'rgba(255, 99, 132, 0.8)',
                        'rgba(54, 162, 235, 0.8)',
                        'rgba(255, 206, 86, 0.8)'
                    ]
                }]
            }
        });

        // Timeline Chart
        const timelineCtx = document.getElementById('timelineChart').getContext('2d');
        timelineChart = new Chart(timelineCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Appointments',
                    data: [],
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1
                }]
            },
            options: {
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

        // Inquiry Chart
        const inquiryCtx = document.getElementById('inquiryChart').getContext('2d');
        inquiryChart = new Chart(inquiryCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Daily Inquiries',
                    data: [],
                    backgroundColor: 'rgba(75, 192, 192, 0.8)'
                }]
            },
            options: {
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

    function updateCharts(appointmentData, inquiryData) {
        // Update service distribution chart
        serviceChart.data.labels = appointmentData.serviceLabels;
        serviceChart.data.datasets[0].data = appointmentData.serviceCounts;
        serviceChart.update();

        // Update timeline chart
        timelineChart.data.labels = appointmentData.timelineLabels;
        timelineChart.data.datasets[0].data = appointmentData.timelineCounts;
        timelineChart.update();

        // Update inquiry chart
        inquiryChart.data.labels = inquiryData.timelineLabels;
        inquiryChart.data.datasets[0].data = inquiryData.timelineCounts;
        inquiryChart.update();
    }
});
