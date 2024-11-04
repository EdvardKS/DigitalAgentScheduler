document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing chatbot...');

    const initChatbot = () => {
        try {
            const elements = {
                chatToggle: document.querySelector('.chat-toggle'),
                chatBody: document.querySelector('.chat-body'),
                chatInput: document.querySelector('.form-control.chat-input'),
                sendButton: document.querySelector('.send-message'),
                chatMessages: document.querySelector('.chat-messages'),
                chatClose: document.querySelector('.chat-close')
            };

            Object.entries(elements).forEach(([key, element]) => {
                console.log(`Element '${key}' found:`, !!element);
                if (!element) {
                    throw new Error(`Required chat element not found: ${key}`);
                }
            });

            let conversationHistory = [];
            let isProcessing = false;
            let retryCount = 0;
            const MAX_RETRIES = 3;
            const RETRY_DELAY = 2000;

            const showError = (message, isTemporary = true) => {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'chat-message system-message error-message';
                errorDiv.innerHTML = `<div class="message-content">${message}</div>`;
                elements.chatMessages.appendChild(errorDiv);
                elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

                if (isTemporary) {
                    setTimeout(() => {
                        errorDiv.remove();
                    }, 5000);
                }
            };

            const showTypingIndicator = () => {
                const typingDiv = document.createElement('div');
                typingDiv.className = 'chat-message bot-message typing-indicator';
                typingDiv.innerHTML = '<div class="message-content"><span>.</span><span>.</span><span>.</span></div>';
                elements.chatMessages.appendChild(typingDiv);
                elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
                return typingDiv;
            };

            const retry = async (fn, retryCount) => {
                try {
                    return await fn();
                } catch (error) {
                    if (retryCount < MAX_RETRIES) {
                        const delay = RETRY_DELAY * Math.pow(2, retryCount);
                        console.log(`Retrying in ${delay}ms... (Attempt ${retryCount + 1}/${MAX_RETRIES})`);
                        await new Promise(resolve => setTimeout(resolve, delay));
                        return retry(fn, retryCount + 1);
                    }
                    throw error;
                }
            };

            const sendMessage = async (message, isUser = true) => {
                console.log(`Sending message (${isUser ? 'user' : 'bot'}):`, message);
                try {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `chat-message ${isUser ? 'user-message' : 'bot-message'}`;
                    messageDiv.innerHTML = `<div class="message-content">${message}</div>`;
                    elements.chatMessages.appendChild(messageDiv);

                    conversationHistory.push({
                        text: message,
                        is_user: isUser
                    });

                    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

                    if (isUser) {
                        elements.chatInput.disabled = true;
                        elements.sendButton.disabled = true;

                        const typingIndicator = showTypingIndicator();

                        try {
                            const response = await retry(async () => {
                                console.log('Making API request...');
                                const res = await fetch('/api/chatbot', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json'
                                    },
                                    body: JSON.stringify({
                                        message,
                                        conversation_history: conversationHistory.slice(0, -1)
                                    })
                                });

                                if (!res.ok) {
                                    const errorData = await res.json();
                                    if (res.status === 429) {
                                        throw new Error('Rate limit exceeded');
                                    }
                                    throw new Error(errorData.error || 'Server error');
                                }

                                return res.json();
                            }, 0);

                            // Remove typing indicator
                            typingIndicator.remove();

                            console.log('API response received:', response);
                            await sendMessage(response.response, false);
                            retryCount = 0;

                            // Handle booking completion
                            if (response.response.includes('BOOKING_COMPLETE')) {
                                showBookingSuccess();
                            }

                        } catch (error) {
                            // Remove typing indicator
                            typingIndicator.remove();

                            console.error('API request error:', error);
                            let errorMessage = 'Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo.';
                            
                            if (error.message === 'Rate limit exceeded') {
                                errorMessage = 'Has enviado demasiados mensajes. Por favor, espera un momento.';
                            } else if (!navigator.onLine) {
                                errorMessage = 'Parece que no hay conexión a internet. Por favor, verifica tu conexión.';
                            }
                            
                            showError(errorMessage);
                        } finally {
                            elements.chatInput.disabled = false;
                            elements.sendButton.disabled = false;
                            elements.chatInput.focus();
                        }
                    }
                } catch (error) {
                    console.error('Message sending error:', error);
                    showError('Error al enviar el mensaje. Por favor, inténtalo de nuevo.');
                }
            };

            const showBookingSuccess = () => {
                // Clear conversation history after successful booking
                conversationHistory = [];
                
                // Show success message with animation
                const successDiv = document.createElement('div');
                successDiv.className = 'chat-message system-message success-message';
                successDiv.innerHTML = `
                    <div class="message-content">
                        <i class="success-icon" data-feather="check-circle"></i>
                        <p>¡Reserva completada con éxito!</p>
                        <small>Revisa tu correo para los detalles de la cita.</small>
                    </div>
                `;
                elements.chatMessages.appendChild(successDiv);
                elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
                
                // Initialize Feather icons for the success message
                feather.replace();
            };

            const handleMessageSend = async () => {
                if (isProcessing) {
                    console.log('Message processing in progress, skipping...');
                    return;
                }

                const message = elements.chatInput.value.trim();
                if (!message) {
                    console.log('Empty message, skipping...');
                    return;
                }

                if (message.length > 500) {
                    showError('El mensaje es demasiado largo. Por favor, acórtalo.');
                    return;
                }

                try {
                    console.log('Processing new message:', message);
                    isProcessing = true;
                    elements.chatInput.value = '';
                    await sendMessage(message);
                } catch (error) {
                    console.error('Message handling error:', error);
                    showError('Error al procesar el mensaje. Por favor, inténtalo de nuevo.');
                } finally {
                    isProcessing = false;
                }
            };

            const setupEventListeners = () => {
                try {
                    elements.chatToggle.addEventListener('click', () => {
                        console.log('Chat toggle clicked');
                        elements.chatBody.style.display = elements.chatBody.style.display === 'none' ? 'flex' : 'none';
                        if (elements.chatBody.style.display === 'flex' && conversationHistory.length === 0) {
                            sendMessage('¡Hola! Soy el asistente virtual de KIT CONSULTING. ¿En qué puedo ayudarte?', false);
                        }
                    });

                    elements.chatClose.addEventListener('click', () => {
                        console.log('Chat close clicked');
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

                    window.addEventListener('online', () => {
                        showError('¡Conexión restaurada!', true);
                    });

                    window.addEventListener('offline', () => {
                        showError('Sin conexión a internet. Los mensajes se enviarán cuando se restaure la conexión.');
                    });

                    elements.chatBody.style.display = 'none';
                    elements.chatToggle.style.display = 'flex';

                    console.log('Event listeners initialized successfully');
                } catch (error) {
                    console.error('Error setting up event listeners:', error);
                }
            };

            setupEventListeners();
            console.log('Chatbot initialization completed successfully');

        } catch (error) {
            console.error('Chatbot initialization error:', error);
        }
    };

    try {
        initChatbot();
    } catch (error) {
        console.error('Fatal chatbot initialization error:', error);
    }
});
