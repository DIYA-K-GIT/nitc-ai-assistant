(function () {
    // 1. Create the UI Container
    const chatContainer = document.createElement('div');
    chatContainer.id = 'nitc-ai-widget';
    chatContainer.innerHTML = `
        <div id="ai-header" style="background:#007bff; color:white; padding:12px; font-family:sans-serif; font-weight:bold; border-radius:15px 15px 0 0;">
            💬 NITC AI Assistant
        </div>
        <div id="ai-messages" style="height:300px; padding:15px; overflow-y:auto; background:#f9f9f9; display:flex; flex-direction:column; gap:10px; font-family:sans-serif; font-size:14px;">
            <div style="background:#e9ecef; padding:10px; border-radius:10px; align-self:flex-start; max-width:85%;">Hello! Ask me about NITC notices or rules.</div>
        </div>
        <div style="display:flex; padding:10px; background:white; border-top:1px solid #ddd; border-radius:0 0 15px 15px;">
            <input type="text" id="ai-input" placeholder="Type a question..." style="flex:1; padding:8px; border:1px solid #ccc; border-radius:5px; outline:none;">
            <button id="ai-send" style="margin-left:8px; padding:8px 15px; background:#007bff; color:white; border:none; border-radius:5px; cursor:pointer;">Send</button>
        </div>
    `;
    
    // 2. Apply Floating CSS
    Object.assign(chatContainer.style, {
        position: 'fixed', bottom: '20px', right: '20px', width: '350px',
        background: 'white', borderRadius: '15px', boxShadow: '0 10px 30px rgba(0,0,0,0.2)',
        border: '1px solid #ddd', zIndex: '999999'
    });
    document.body.appendChild(chatContainer);

    // 3. Setup Chat Logic
    const input = document.getElementById('ai-input');
    const sendBtn = document.getElementById('ai-send');
    const messages = document.getElementById('ai-messages');

    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        // Add user message to UI
        messages.innerHTML += `<div style="background:#007bff; color:white; padding:10px; border-radius:10px; align-self:flex-end; max-width:85%;">${text}</div>`;
        input.value = '';
        
        // Add loading indicator
        const loadingId = 'loading-' + Date.now();
        messages.innerHTML += `<div id="${loadingId}" style="background:#e9ecef; padding:10px; border-radius:10px; align-self:flex-start; max-width:85%; font-style:italic;">Analyzing rules...</div>`;
        messages.scrollTop = messages.scrollHeight;

        try {
            // Hit your local Python API
            const response = await fetch('http://127.0.0.1:8000/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: text })
            });
            const data = await response.json();
            
            // Replace loading indicator with real answer
            document.getElementById(loadingId).outerHTML = `<div style="background:#e9ecef; padding:10px; border-radius:10px; align-self:flex-start; max-width:85%; line-height:1.4;">${data.answer}</div>`;
        } catch (error) {
            document.getElementById(loadingId).outerHTML = `<div style="background:#ffebee; color:#c62828; padding:10px; border-radius:10px; align-self:flex-start; max-width:85%;">Error connecting to local AI engine.</div>`;
        }
        messages.scrollTop = messages.scrollHeight;
    }

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
})();