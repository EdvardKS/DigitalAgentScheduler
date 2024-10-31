// Initialize Feather Icons
document.addEventListener('DOMContentLoaded', () => {
    feather.replace();

    // Navbar and logo elements
    const navbar = document.querySelector('.navbar');
    const logo = document.querySelector('.nav-logo');
    
    // Navbar scroll behavior with logo color change
    const checkScroll = () => {
        const scrollPosition = window.scrollY;
        
        if (scrollPosition > 50) {
            navbar.classList.add('scrolled');
            logo.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
            logo.classList.remove('scrolled');
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
