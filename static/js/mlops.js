document.addEventListener('DOMContentLoaded', () => {
    const PIN = '1997';
    const pinModal = new bootstrap.Modal(document.getElementById('pinModal'));
    const dashboardContent = document.getElementById('dashboardContent');

    // Show PIN modal on page load
    pinModal.show();

    // PIN verification
    document.getElementById('verifyPin').addEventListener('click', () => {
        const enteredPin = document.getElementById('pinInput').value;
        if (enteredPin === PIN) {
            pinModal.hide();
            dashboardContent.style.display = 'block';
            initializeDashboard();
        } else {
            document.getElementById('pinInput').classList.add('is-invalid');
        }
    });

    // Initialize performance chart
    function initializeDashboard() {
        const ctx = document.getElementById('performanceChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: Array.from({length: 7}, (_, i) => {
                    const d = new Date();
                    d.setDate(d.getDate() - i);
                    return d.toLocaleDateString();
                }).reverse(),
                datasets: [{
                    label: 'Response Time (ms)',
                    data: [150, 145, 160, 155, 140, 150, 145],
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });

        // Initialize metrics
        updateMetrics();
    }

    // Update dashboard metrics
    function updateMetrics() {
        document.getElementById('avgResponseTime').textContent = '145 ms';
        document.getElementById('successRate').textContent = '98.5%';
        document.getElementById('dailyQueries').textContent = '1,234';
    }

    // Fine-tuning form submission
    document.getElementById('finetuneForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const trainingData = document.getElementById('trainingData').value;
        const epochs = document.getElementById('epochs').value;

        try {
            const response = await fetch('/api/finetune', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ trainingData, epochs })
            });
            
            if (response.ok) {
                alert('Fine-tuning process started successfully!');
            } else {
                alert('Error starting fine-tuning process');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error starting fine-tuning process');
        }
    });

    // Security settings save
    document.getElementById('saveSecuritySettings')?.addEventListener('click', async () => {
        const settings = {
            profanityFilter: document.getElementById('profanityFilter').checked,
            inputValidation: document.getElementById('inputValidation').checked,
            maxPromptLength: document.getElementById('maxPromptLength').value
        };

        try {
            const response = await fetch('/api/security-settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(settings)
            });
            
            if (response.ok) {
                alert('Security settings saved successfully!');
            } else {
                alert('Error saving security settings');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error saving security settings');
        }
    });
});
