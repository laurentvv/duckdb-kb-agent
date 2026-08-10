document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('askForm');
    const input = document.getElementById('questionInput');
    const sendBtn = document.getElementById('sendBtn');
    const chatContainer = document.getElementById('chatContainer');

    function scrollToBottom() {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function addMessage(content, type, sources = [], interactionId = null) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${type}-msg`;

        const contentDiv = document.createElement('div');
        contentDiv.className = 'msg-content';
        
        // Use marked.js for bot messages, plain text for user
        if (type === 'bot') {
            contentDiv.innerHTML = marked.parse(content);
        } else {
            contentDiv.textContent = content;
        }

        msgDiv.appendChild(contentDiv);

        // Add sources if available
        if (sources && sources.length > 0) {
            const sourcesDiv = document.createElement('div');
            sourcesDiv.className = 'msg-sources';
            
            // Extract unique filenames
            const uniqueSources = [...new Set(sources.map(s => s.split('\\').pop().split('/').pop()))];
            
            uniqueSources.forEach(source => {
                const badge = document.createElement('span');
                badge.className = 'source-badge';
                badge.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                    ${source}
                `;
                sourcesDiv.appendChild(badge);
            });
            msgDiv.appendChild(sourcesDiv);
        }


        // Add feedback UI if bot message and interactionId exists
        if (type === 'bot' && interactionId) {
            const feedbackDiv = document.createElement('div');
            feedbackDiv.className = 'feedback-container';
            feedbackDiv.innerHTML = `
                <div class="feedback-buttons">
                    <button class="feedback-btn thumbs-up" data-id="${interactionId}" data-rating="up" title="Bonne réponse">👍</button>
                    <button class="feedback-btn thumbs-down" data-id="${interactionId}" data-rating="down" title="Mauvaise réponse">👎</button>
                </div>
                <div class="feedback-comment-form" id="feedback-form-${interactionId}" style="display: none;">
                    <input type="text" placeholder="Dites-nous ce qui n'allait pas..." class="feedback-input" id="feedback-input-${interactionId}">
                    <button class="feedback-submit-btn" data-id="${interactionId}">Envoyer</button>
                </div>
            `;
            msgDiv.appendChild(feedbackDiv);

            // Event listeners
            setTimeout(() => {
                const upBtn = feedbackDiv.querySelector('.thumbs-up');
                const downBtn = feedbackDiv.querySelector('.thumbs-down');
                const form = feedbackDiv.querySelector(`#feedback-form-${interactionId}`);
                const submitBtn = feedbackDiv.querySelector('.feedback-submit-btn');
                const input = feedbackDiv.querySelector(`#feedback-input-${interactionId}`);

                upBtn.addEventListener('click', () => {
                    sendFeedback(interactionId, 'up');
                    upBtn.classList.add('active');
                    downBtn.classList.remove('active');
                    form.style.display = 'none';
                });

                downBtn.addEventListener('click', () => {
                    sendFeedback(interactionId, 'down');
                    downBtn.classList.add('active');
                    upBtn.classList.remove('active');
                    form.style.display = 'flex';
                });

                submitBtn.addEventListener('click', () => {
                    const comment = input.value.trim();
                    sendFeedback(interactionId, 'down', comment);
                    form.innerHTML = '<span class="feedback-thanks">Merci pour votre retour !</span>';
                });
            }, 100);
        }

        chatContainer.appendChild(msgDiv);
        scrollToBottom();
    }

    function addTypingIndicator() {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message bot-msg typing-indicator-container';
        msgDiv.id = 'typingIndicator';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'msg-content typing-indicator';
        contentDiv.innerHTML = `
            <div class="dot"></div>
            <div class="dot"></div>
            <div class="dot"></div>
        `;
        
        msgDiv.appendChild(contentDiv);

        // Add feedback UI if bot message and interactionId exists
        if (type === 'bot' && interactionId) {
            const feedbackDiv = document.createElement('div');
            feedbackDiv.className = 'feedback-container';
            feedbackDiv.innerHTML = `
                <div class="feedback-buttons">
                    <button class="feedback-btn thumbs-up" data-id="${interactionId}" data-rating="up" title="Bonne réponse">👍</button>
                    <button class="feedback-btn thumbs-down" data-id="${interactionId}" data-rating="down" title="Mauvaise réponse">👎</button>
                </div>
                <div class="feedback-comment-form" id="feedback-form-${interactionId}" style="display: none;">
                    <input type="text" placeholder="Dites-nous ce qui n'allait pas..." class="feedback-input" id="feedback-input-${interactionId}">
                    <button class="feedback-submit-btn" data-id="${interactionId}">Envoyer</button>
                </div>
            `;
            msgDiv.appendChild(feedbackDiv);

            // Event listeners
            setTimeout(() => {
                const upBtn = feedbackDiv.querySelector('.thumbs-up');
                const downBtn = feedbackDiv.querySelector('.thumbs-down');
                const form = feedbackDiv.querySelector(`#feedback-form-${interactionId}`);
                const submitBtn = feedbackDiv.querySelector('.feedback-submit-btn');
                const input = feedbackDiv.querySelector(`#feedback-input-${interactionId}`);

                upBtn.addEventListener('click', () => {
                    sendFeedback(interactionId, 'up');
                    upBtn.classList.add('active');
                    downBtn.classList.remove('active');
                    form.style.display = 'none';
                });

                downBtn.addEventListener('click', () => {
                    sendFeedback(interactionId, 'down');
                    downBtn.classList.add('active');
                    upBtn.classList.remove('active');
                    form.style.display = 'flex';
                });

                submitBtn.addEventListener('click', () => {
                    const comment = input.value.trim();
                    sendFeedback(interactionId, 'down', comment);
                    form.innerHTML = '<span class="feedback-thanks">Merci pour votre retour !</span>';
                });
            }, 100);
        }

        chatContainer.appendChild(msgDiv);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
            indicator.remove();
        }
    }


    function sendFeedback(interactionId, rating, comment = "") {
        fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ interaction_id: interactionId, rating: rating, comment: comment })
        }).catch(err => console.error("Erreur feedback:", err));
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const question = input.value.trim();
        if (!question) return;

        // Disable input
        input.value = '';
        input.disabled = true;
        sendBtn.disabled = true;

        // Add user message
        addMessage(question, 'user');
        
        // Add typing indicator
        addTypingIndicator();

        try {
            const response = await fetch('/api/ask', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ question })
            });

            removeTypingIndicator();
            
            // Create a message placeholder
            const msgDiv = document.createElement('div');
            msgDiv.className = `message bot-msg`;
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'msg-content';
            msgDiv.appendChild(contentDiv);
            

        // Add feedback UI if bot message and interactionId exists
        if (type === 'bot' && interactionId) {
            const feedbackDiv = document.createElement('div');
            feedbackDiv.className = 'feedback-container';
            feedbackDiv.innerHTML = `
                <div class="feedback-buttons">
                    <button class="feedback-btn thumbs-up" data-id="${interactionId}" data-rating="up" title="Bonne réponse">👍</button>
                    <button class="feedback-btn thumbs-down" data-id="${interactionId}" data-rating="down" title="Mauvaise réponse">👎</button>
                </div>
                <div class="feedback-comment-form" id="feedback-form-${interactionId}" style="display: none;">
                    <input type="text" placeholder="Dites-nous ce qui n'allait pas..." class="feedback-input" id="feedback-input-${interactionId}">
                    <button class="feedback-submit-btn" data-id="${interactionId}">Envoyer</button>
                </div>
            `;
            msgDiv.appendChild(feedbackDiv);

            // Event listeners
            setTimeout(() => {
                const upBtn = feedbackDiv.querySelector('.thumbs-up');
                const downBtn = feedbackDiv.querySelector('.thumbs-down');
                const form = feedbackDiv.querySelector(`#feedback-form-${interactionId}`);
                const submitBtn = feedbackDiv.querySelector('.feedback-submit-btn');
                const input = feedbackDiv.querySelector(`#feedback-input-${interactionId}`);

                upBtn.addEventListener('click', () => {
                    sendFeedback(interactionId, 'up');
                    upBtn.classList.add('active');
                    downBtn.classList.remove('active');
                    form.style.display = 'none';
                });

                downBtn.addEventListener('click', () => {
                    sendFeedback(interactionId, 'down');
                    downBtn.classList.add('active');
                    upBtn.classList.remove('active');
                    form.style.display = 'flex';
                });

                submitBtn.addEventListener('click', () => {
                    const comment = input.value.trim();
                    sendFeedback(interactionId, 'down', comment);
                    form.innerHTML = '<span class="feedback-thanks">Merci pour votre retour !</span>';
                });
            }, 100);
        }

        chatContainer.appendChild(msgDiv);
            
            let fullText = '';
            let sourcesAdded = false;
            let currentInteractionId = null;

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, {stream: true});
                let newlineIdx;
                
                while ((newlineIdx = buffer.indexOf('\n\n')) >= 0) {
                    const message = buffer.slice(0, newlineIdx);
                    buffer = buffer.slice(newlineIdx + 2);
                    
                    if (message.startsWith('data: ')) {
                        const dataStr = message.slice(6);
                        if (dataStr === '[DONE]') continue;
                        
                        try {
                            const data = JSON.parse(dataStr);
                            
                            if (data.interaction_id) {
                                currentInteractionId = data.interaction_id;
                            }
                            if (data.sources && !sourcesAdded) {
                                const sourcesDiv = document.createElement('div');
                                sourcesDiv.className = 'msg-sources';
                                
                                data.sources.forEach(source => {
                                    const badge = document.createElement('span');
                                    badge.className = 'source-badge';
                                    badge.innerHTML = `
                                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                                        ${source}
                                    `;
                                    sourcesDiv.appendChild(badge);
                                });
                                msgDiv.appendChild(sourcesDiv);
                                sourcesAdded = true;
                            }
                            
                            if (data.chunk) {
                                fullText += data.chunk;
                                contentDiv.innerHTML = marked.parse(fullText);
                                scrollToBottom();
                            }
                        } catch(e) {
                            console.error("Error parsing JSON", e, dataStr);
                        }
                    }
                }
            }

            // À la fin du stream, on injecte les boutons de feedback dans msgDiv
            if (currentInteractionId) {
                const feedbackDiv = document.createElement('div');
                feedbackDiv.className = 'feedback-container';
                feedbackDiv.innerHTML = `
                    <div class="feedback-buttons">
                        <button class="feedback-btn thumbs-up" data-id="${currentInteractionId}" data-rating="up" title="Bonne réponse">👍</button>
                        <button class="feedback-btn thumbs-down" data-id="${currentInteractionId}" data-rating="down" title="Mauvaise réponse">👎</button>
                    </div>
                    <div class="feedback-comment-form" id="feedback-form-${currentInteractionId}" style="display: none;">
                        <input type="text" placeholder="Dites-nous ce qui n'allait pas..." class="feedback-input" id="feedback-input-${currentInteractionId}">
                        <button class="feedback-submit-btn" data-id="${currentInteractionId}">Envoyer</button>
                    </div>
                `;
                msgDiv.appendChild(feedbackDiv);

                const upBtn = feedbackDiv.querySelector('.thumbs-up');
                const downBtn = feedbackDiv.querySelector('.thumbs-down');
                const fForm = feedbackDiv.querySelector(`#feedback-form-${currentInteractionId}`);
                const submitBtn = feedbackDiv.querySelector('.feedback-submit-btn');
                const fInput = feedbackDiv.querySelector(`#feedback-input-${currentInteractionId}`);

                upBtn.addEventListener('click', () => {
                    sendFeedback(currentInteractionId, 'up');
                    upBtn.classList.add('active');
                    downBtn.classList.remove('active');
                    fForm.style.display = 'none';
                });

                downBtn.addEventListener('click', () => {
                    sendFeedback(currentInteractionId, 'down');
                    downBtn.classList.add('active');
                    upBtn.classList.remove('active');
                    fForm.style.display = 'flex';
                });

                submitBtn.addEventListener('click', () => {
                    const comment = fInput.value.trim();
                    sendFeedback(currentInteractionId, 'down', comment);
                    fForm.innerHTML = '<span class="feedback-thanks">Merci pour votre retour !</span>';
                });
                scrollToBottom();
            }

        } catch (error) {
            console.error('Error:', error);
            removeTypingIndicator();
            addMessage("Désolé, une erreur de communication avec le serveur est survenue.", 'system');
        } finally {
            // Re-enable input
            input.disabled = false;
            sendBtn.disabled = false;
            input.focus();
        }
    });

    // Initial focus
    input.focus();
});
