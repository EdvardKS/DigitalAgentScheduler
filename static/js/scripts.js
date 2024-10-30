// scripts.js

// Agregar funcionalidad al hacer clic en los iconos sociales o enlaces
document.addEventListener("DOMContentLoaded", () => {
    const socialLinks = document.querySelectorAll(".footer-social-icons a");
    const privacyLinks = document.querySelectorAll("footer .privacy-link");

    // Efecto al hacer clic en los iconos sociales
    socialLinks.forEach(link => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
            const url = link.getAttribute("href");
            window.open(url, "_blank"); // Abrir en una nueva pestaña
        });
    });

    // Efecto de resaltar para los enlaces de privacidad (opcional)
    privacyLinks.forEach(link => {
        link.addEventListener("click", () => {
            link.style.color = "#ffcccc";
            setTimeout(() => link.style.color = "white", 300);
        });
    });
});
