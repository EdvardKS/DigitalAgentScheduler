document.addEventListener('DOMContentLoaded', () => {
    const chatToggle = document.querySelector('.chat-toggle');
    const chatBody = document.querySelector('.chat-body');
    const chatInput = document.querySelector('.chat-input input');
    const sendButton = document.querySelector('.send-message');
    const chatMessages = document.querySelector('.chat-messages');

    let conversationHistory = [];

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
        if (chatBody.style.display === 'flex' && conversationHistory.length === 0) {
            // Send initial greeting
            sendMessage("¡Hola! ¿En qué puedo ayudarte?", false);
        }
    });

    // Send message function
    const sendMessage = async (message, isUser = true) => {
        // Create message element
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${isUser ? 'user-message' : 'bot-message'}`;
        messageDiv.innerHTML = `
            <div class="message-content">
                ${message}
            </div>
        `;
        chatMessages.appendChild(messageDiv);

        // Save to conversation history
        conversationHistory.push({
            text: message,
            is_user: isUser
        });

        // Scroll to bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;

        // If it's a user message, get bot response
        if (isUser) {
            try {
                const response = await fetch('/api/chatbot', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        message: message,
                        conversation_history: conversationHistory.slice(0, -1) // Exclude current message
                    })
                });

                if (response.ok) {
                    const data = await response.json();
                    sendMessage(data.response, false);
                } else {
                    throw new Error('Error en la respuesta del servidor');
                }
            } catch (error) {
                console.error('Error:', error);
                sendMessage('Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo.', false);
            }
        }
    };

    // Handle send button click
    sendButton.addEventListener('click', () => {
        const message = chatInput.value.trim();
        if (message) {
            sendMessage(message);
            chatInput.value = '';
        }
    });

    // Handle enter key
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const message = chatInput.value.trim();
            if (message) {
                sendMessage(message);
                chatInput.value = '';
            }
        }
    });

    // Add some basic styles
    const style = document.createElement('style');
    style.textContent = `
        .chat-message {
            margin: 10px;
            padding: 10px;
            border-radius: 10px;
            max-width: 80%;
        }

        .user-message {
            background-color: #d8001d;
            color: white;
            margin-left: auto;
        }

        .bot-message {
            background-color: #f8f9fa;
            color: #333;
            margin-right: auto;
        }

        .message-content {
            word-wrap: break-word;
        }
    `;
    document.head.appendChild(style);
});
