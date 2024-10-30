document.addEventListener('DOMContentLoaded', () => {
    // Initialize chatbot with proper error handling
    const initChatbot = () => {
        try {
            // DOM Elements with null checks
            const elements = {
                chatToggle: document.querySelector('.chat-toggle'),
                chatBody: document.querySelector('.chat-body'),
                chatInput: document.querySelector('.chat-input input'),
                sendButton: document.querySelector('.send-message'),
                chatMessages: document.querySelector('.chat-messages'),
                chatClose: document.querySelector('.chat-close')
            };

            // Validate all required elements exist
            Object.entries(elements).forEach(([key, element]) => {
                if (!element) {
                    throw new Error(`Required chat element not found: ${key}`);
                }
            });

            // State management
            let conversationHistory = [];
            let isProcessing = false;

            // Send message function
            const sendMessage = async (message, isUser = true) => {
                try {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `chat-message ${isUser ? 'user-message' : 'bot-message'}`;
                    messageDiv.innerHTML = `<div class="message-content">${message}</div>`;
                    elements.chatMessages.appendChild(messageDiv);

                    // Update conversation history
                    conversationHistory.push({
                        text: message,
                        is_user: isUser
                    });

                    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

                    if (isUser) {
                        elements.chatInput.disabled = true;
                        elements.sendButton.disabled = true;

                        try {
                            const response = await fetch('/api/chatbot', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json'
                                },
                                body: JSON.stringify({
                                    message,
                                    conversation_history: conversationHistory.slice(0, -1)
                                })
                            });

                            if (!response.ok) {
                                throw new Error(`HTTP error! status: ${response.status}`);
                            }

                            const data = await response.json();
                            await sendMessage(data.response, false);
                        } finally {
                            elements.chatInput.disabled = false;
                            elements.sendButton.disabled = false;
                            elements.chatInput.focus();
                        }
                    }
                } catch (error) {
                    console.error('Chatbot Error [send-message]:', error);
                    if (isUser) {
                        await sendMessage('Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo.', false);
                    }
                }
            };

            // Event handler for sending messages
            const handleMessageSend = async () => {
                if (isProcessing) return;

                const message = elements.chatInput.value.trim();
                if (!message) return;

                try {
                    isProcessing = true;
                    elements.chatInput.value = '';
                    await sendMessage(message);
                } catch (error) {
                    console.error('Chatbot Error [handle-message]:', error);
                } finally {
                    isProcessing = false;
                }
            };

            // Event Listeners
            elements.chatToggle.addEventListener('click', () => {
                const isHidden = elements.chatBody.style.display === 'none';
                elements.chatBody.style.display = isHidden ? 'flex' : 'none';
                
                if (isHidden && conversationHistory.length === 0) {
                    sendMessage('¡Hola! Soy el asistente virtual de KIT CONSULTING. ¿En qué puedo ayudarte a entender nuestro programa de ayudas?', false);
                }
            });

            elements.chatClose.addEventListener('click', () => {
                elements.chatBody.style.display = 'none';
            });

            elements.sendButton.addEventListener('click', (e) => {
                e.preventDefault();
                handleMessageSend();
            });

            elements.chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleMessageSend();
                }
            });

            // Initialize UI state
            elements.chatBody.style.display = 'none';
            elements.chatToggle.style.display = 'flex';
            elements.chatToggle.style.visibility = 'visible';

        } catch (error) {
            console.error('Chatbot Error [initialization]:', error);
        }
    };

    // Initialize chatbot
    initChatbot();
});
