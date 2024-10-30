document.addEventListener('DOMContentLoaded', () => {
    // Initialize DOM elements with null checks
    const chatToggle = document.querySelector('.chat-toggle');
    const chatBody = document.querySelector('.chat-body');
    const chatInput = document.querySelector('.chat-input input');
    const sendButton = document.querySelector('.send-message');
    const chatMessages = document.querySelector('.chat-messages');
    const chatClose = document.querySelector('.chat-close');

    // Initialize conversation history
    let conversationHistory = [];

    // Error logging function
    const logError = (error, context) => {
        console.error(`Chatbot Error [${context}]:`, error);
    };

    // Initialize chat UI if elements exist
    if (chatToggle && chatBody) {
        try {
            // Ensure chat button visibility
            chatToggle.style.display = 'flex';
            chatToggle.style.visibility = 'visible';
            chatToggle.style.opacity = '1';
            chatToggle.style.zIndex = '9999';

            // Toggle chat window
            chatToggle.addEventListener('click', () => {
                try {
                    chatBody.style.display = chatBody.style.display === 'none' ? 'flex' : 'none';
                    if (chatBody.style.display === 'flex' && conversationHistory.length === 0) {
                        // Send initial greeting
                        sendMessage("¡Hola! ¿En qué puedo ayudarte con el programa KIT CONSULTING?", false);
                    }
                } catch (error) {
                    logError(error, 'chat-toggle');
                }
            });

            // Close chat window
            if (chatClose) {
                chatClose.addEventListener('click', () => {
                    try {
                        chatBody.style.display = 'none';
                    } catch (error) {
                        logError(error, 'chat-close');
                    }
                });
            }
        } catch (error) {
            logError(error, 'chat-initialization');
        }
    }

    // Send message function
    const sendMessage = async (message, isUser = true) => {
        try {
            if (!chatMessages) {
                throw new Error('Chat messages container not found');
            }

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
                            conversation_history: conversationHistory.slice(0, -1)
                        })
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const data = await response.json();
                    sendMessage(data.response, false);
                } catch (error) {
                    logError(error, 'api-request');
                    sendMessage('Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo.', false);
                }
            }
        } catch (error) {
            logError(error, 'send-message');
        }
    };

    // Set up input handling if elements exist
    if (chatInput && sendButton) {
        try {
            // Handle send button click
            sendButton.addEventListener('click', (e) => {
                try {
                    e.preventDefault();
                    const message = chatInput.value.trim();
                    if (message) {
                        sendMessage(message);
                        chatInput.value = '';
                    }
                } catch (error) {
                    logError(error, 'send-button');
                }
            });

            // Handle enter key
            chatInput.addEventListener('keypress', (e) => {
                try {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        const message = chatInput.value.trim();
                        if (message) {
                            sendMessage(message);
                            chatInput.value = '';
                        }
                    }
                } catch (error) {
                    logError(error, 'input-keypress');
                }
            });
        } catch (error) {
            logError(error, 'input-setup');
        }
    }

    // Add styles
    const style = document.createElement('style');
    style.textContent = `
        .chat-message {
            margin: 10px;
            padding: 10px;
            border-radius: 10px;
            max-width: 80%;
            word-break: break-word;
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
            white-space: pre-wrap;
        }
    `;
    document.head.appendChild(style);
});
