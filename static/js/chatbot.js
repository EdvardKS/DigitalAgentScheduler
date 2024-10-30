document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing chatbot...');

    const initChatbot = () => {
        try {
            // DOM Elements with detailed error logging
            const elements = {
                chatToggle: document.querySelector('.chat-toggle'),
                chatBody: document.querySelector('.chat-body'),
                chatInput: document.querySelector('.form-control.chat-input'),
                sendButton: document.querySelector('.send-message'),
                chatMessages: document.querySelector('.chat-messages'),
                chatClose: document.querySelector('.chat-close')
            };

            // Log element status and validate
            Object.entries(elements).forEach(([key, element]) => {
                console.log(`Element '${key}' found:`, !!element);
                if (!element) {
                    throw new Error(`Required chat element not found: ${key}`);
                }
            });

            // State management
            let conversationHistory = [];
            let isProcessing = false;

            // Send message function with enhanced error handling
            const sendMessage = async (message, isUser = true) => {
                console.log(`Sending message (${isUser ? 'user' : 'bot'}):`, message);
                try {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `chat-message ${isUser ? 'user-message' : 'bot-message'}`;
                    messageDiv.innerHTML = `<div class="message-content">${message}</div>`;
                    elements.chatMessages.appendChild(messageDiv);

                    // Save message to conversation history
                    conversationHistory.push({
                        text: message,
                        is_user: isUser
                    });

                    // Auto-scroll to latest message
                    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

                    if (isUser) {
                        // Disable input during processing
                        elements.chatInput.disabled = true;
                        elements.sendButton.disabled = true;

                        try {
                            console.log('Making API request...');
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
                            console.log('API response received:', data);
                            await sendMessage(data.response, false);
                        } catch (error) {
                            console.error('API request error:', error);
                            await sendMessage('Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo.', false);
                        } finally {
                            // Re-enable input after processing
                            elements.chatInput.disabled = false;
                            elements.sendButton.disabled = false;
                            elements.chatInput.focus();
                        }
                    }
                } catch (error) {
                    console.error('Message sending error:', error);
                }
            };

            // Message handler with improved error handling
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

                try {
                    console.log('Processing new message:', message);
                    isProcessing = true;
                    elements.chatInput.value = '';
                    await sendMessage(message);
                } catch (error) {
                    console.error('Message handling error:', error);
                } finally {
                    isProcessing = false;
                }
            };

            // Event Listeners with error boundaries
            const setupEventListeners = () => {
                try {
                    // Toggle chat window
                    elements.chatToggle.addEventListener('click', () => {
                        console.log('Chat toggle clicked');
                        elements.chatBody.style.display = elements.chatBody.style.display === 'none' ? 'flex' : 'none';
                        if (elements.chatBody.style.display === 'flex' && conversationHistory.length === 0) {
                            sendMessage('¡Hola! Soy el asistente virtual de KIT CONSULTING. ¿En qué puedo ayudarte a entender nuestro programa de ayudas?', false);
                        }
                    });

                    // Close chat window
                    elements.chatClose.addEventListener('click', () => {
                        console.log('Chat close clicked');
                        elements.chatBody.style.display = 'none';
                    });

                    // Send message button
                    elements.sendButton.addEventListener('click', (e) => {
                        e.preventDefault();
                        handleMessageSend();
                    });

                    // Send message on Enter
                    elements.chatInput.addEventListener('keypress', (e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleMessageSend();
                        }
                    });

                    // Initialize UI state
                    elements.chatBody.style.display = 'none';
                    elements.chatToggle.style.display = 'flex';

                    console.log('Event listeners initialized successfully');
                } catch (error) {
                    console.error('Error setting up event listeners:', error);
                }
            };

            // Initialize event listeners
            setupEventListeners();
            console.log('Chatbot initialization completed successfully');

        } catch (error) {
            console.error('Chatbot initialization error:', error);
        }
    };

    // Initialize chatbot with error boundary
    try {
        initChatbot();
    } catch (error) {
        console.error('Fatal chatbot initialization error:', error);
    }
});
