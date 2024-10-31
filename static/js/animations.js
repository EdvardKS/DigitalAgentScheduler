// Initialize Feather Icons
document.addEventListener('DOMContentLoaded', () => {
    feather.replace();

    // Navbar and logo elements
    const navbar = document.querySelector('.navbar');
    const logo = document.querySelector('.nav-logo');
    const navLinks = document.querySelectorAll('.nav-link');
    
    // Navbar scroll behavior with logo color change
    const checkScroll = () => {
        const scrollPosition = window.scrollY;
        
        if (scrollPosition > 0) {
            navbar.classList.add('scrolled');
            // Change to red (#d8001d)
            logo.style.color = '#d8001d';
            // Update nav link colors when scrolled
            navLinks.forEach(link => {
                link.style.color = '#333333 !important';
            });
            // Backup filter method if needed
            logo.style.filter = 'invert(13%) sepia(75%) saturate(4407%) hue-rotate(341deg) brightness(91%) contrast(122%)';
        } else {
            navbar.classList.remove('scrolled');
            // Reset to white
            logo.style.color = '#ffffff';
            // Reset nav link colors
            navLinks.forEach(link => {
                link.style.color = '#ffffff !important';
            });
            // Backup filter method if needed
            logo.style.filter = 'brightness(0) invert(1)';
        }
    };

    window.addEventListener('scroll', checkScroll);
    checkScroll(); // Initial check

    // Animate elements on scroll
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Observe elements with animation classes
    document.querySelectorAll('.fade-in, .slide-in').forEach(element => {
        observer.observe(element);
    });
});
