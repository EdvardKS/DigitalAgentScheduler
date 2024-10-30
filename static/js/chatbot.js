document.addEventListener('DOMContentLoaded', () => {
    const chatToggle = document.querySelector('.chat-toggle');
    const chatBody = document.querySelector('.chat-body');
    const chatInput = document.querySelector('.chat-input input');
    const sendButton = document.querySelector('.send-message');
    const chatMessages = document.querySelector('.chat-messages');

    // Ensure chat button visibility
    if (chatToggle) {
        chatToggle.style.display = 'flex';
        chatToggle.style.visibility = 'visible';
        chatToggle.style.opacity = '1';
        chatToggle.style.zIndex = '9999';
    }

    // Toggle chat window
    chatToggle.addEventListener('click', () => {
        chatBody.style.display = chatBody.style.display === 'none' ? 'flex' : 'none';
    });

    // Rest of the chatbot.js code remains unchanged...
});
