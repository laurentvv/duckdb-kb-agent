document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('askForm');
    const input = document.getElementById('questionInput');
    const sendBtn = document.getElementById('sendBtn');
    const chatContainer = document.getElementById('chatContainer');

    function scrollToBottom() {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function addMessage(content, type, sources = []) {
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
        chatContainer.appendChild(msgDiv);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
            indicator.remove();
        }
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
            
            chatContainer.appendChild(msgDiv);
            
            let fullText = '';
            let sourcesAdded = false;

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
