(function () {
    const style = document.createElement('style');
    style.innerHTML = `
        #nitc-bot-toggle {
            position: fixed; bottom: 20px; right: 20px;
            width: 60px; height: 60px; border-radius: 50%;
            background-color: #007bff; color: white; border: none;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15); cursor: pointer;
            font-size: 24px; z-index: 999999; transition: transform 0.2s ease;
        }
        #nitc-bot-toggle:hover { transform: scale(1.05); }
    `;
    document.head.appendChild(style);
    const toggleBtn = document.createElement('button');
    toggleBtn.id = 'nitc-bot-toggle';
    toggleBtn.innerHTML = '💬';
    document.body.appendChild(toggleBtn);

    const chatContainer = document.createElement('div');
    chatContainer.id = 'nitc-ai-widget';
    chatContainer.innerHTML = `
        <div id="ai-header" style="background:#007bff; color:white; padding:12px; font-family:sans-serif; font-weight:bold; border-radius:15px 15px 0 0; display:flex; justify-content:space-between; align-items:center;">
            <span>💬 NITC Query Bot</span>
            <button id="ai-close" style="background:none; border:none; color:white; font-size:20px; cursor:pointer;">&times;</button>
        </div>
        <div id="ai-messages" style="height:350px; padding:15px; overflow-y:auto; background:#f9f9f9; display:flex; flex-direction:column; gap:10px; font-family:sans-serif; font-size:14px;">
            <div style="background:#e9ecef; padding:10px; border-radius:10px; align-self:flex-start; max-width:85%;">Hello! Ask me about NITC academic rules and regulations.</div>
        </div>
        <div style="display:flex; padding:10px; background:white; border-top:1px solid #ddd; border-radius:0 0 15px 15px;">
            <input type="text" id="ai-input" placeholder="Type a question..." style="flex:1; padding:8px; border:1px solid #ccc; border-radius:20px; outline:none; padding-left:15px;">
            <button id="ai-send" style="margin-left:8px; width:38px; height:38px; background:#007bff; color:white; border:none; border-radius:50%; cursor:pointer; font-weight:bold;">➤</button>
        </div>
    `;
    
    Object.assign(chatContainer.style, {
        position: 'fixed', bottom: '90px', right: '20px', width: '350px',
        background: 'white', borderRadius: '15px', boxShadow: '0 10px 30px rgba(0,0,0,0.2)',
        border: '1px solid #ddd', zIndex: '999999', display: 'none', flexDirection: 'column'
    });
    document.body.appendChild(chatContainer);

    const input = document.getElementById('ai-input');
    const sendBtn = document.getElementById('ai-send');
    const messages = document.getElementById('ai-messages');
    const closeBtn = document.getElementById('ai-close');
    const savedMessages = sessionStorage.getItem('nitcChatHistory');
    if (savedMessages) {
        messages.innerHTML = savedMessages;
    }
    if (sessionStorage.getItem('nitcChatState') === 'open') {
        chatContainer.style.display = 'flex';
        toggleBtn.style.display = 'none';
        messages.scrollTop = messages.scrollHeight;
    }

    function saveChatState() {
        sessionStorage.setItem('nitcChatHistory', messages.innerHTML);
    }
   
    toggleBtn.addEventListener('click', () => {
        chatContainer.style.display = 'flex';
        toggleBtn.style.display = 'none';
        sessionStorage.setItem('nitcChatState', 'open'); 
        messages.scrollTop = messages.scrollHeight;
    });

    closeBtn.addEventListener('click', () => {
        chatContainer.style.display = 'none';
        toggleBtn.style.display = 'block';
        sessionStorage.setItem('nitcChatState', 'closed'); 
    });
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        messages.innerHTML += `<div style="background:#007bff; color:white; padding:10px; border-radius:10px 10px 2px 10px; align-self:flex-end; max-width:85%; font-family:sans-serif; font-size:14px;">${text}</div>`;
        input.value = '';
        const loadingId = 'loading-' + Date.now();
        messages.innerHTML += `<div id="${loadingId}" style="background:#e9ecef; padding:10px; border-radius:10px 10px 10px 2px; align-self:flex-start; max-width:85%; font-style:italic; font-family:sans-serif; font-size:14px;">Analyzing rules...</div>`;
        
        messages.scrollTop = messages.scrollHeight;
        saveChatState(); 

        try {
            const response = await fetch('http://127.0.0.1:8000/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: text })
            });
            const data = await response.json();
            
            const isError = data.answer.includes("cannot find that information");
            const errorStyle = isError ? "border-left: 4px solid #dc3545;" : "";

            document.getElementById(loadingId).outerHTML = `<div style="background:#e9ecef; padding:10px; border-radius:10px 10px 10px 2px; align-self:flex-start; max-width:85%; line-height:1.4; font-family:sans-serif; font-size:14px; white-space:pre-wrap; ${errorStyle}">${data.answer}</div>`;
        } catch (error) {
            document.getElementById(loadingId).outerHTML = `<div style="background:#ffebee; color:#c62828; padding:10px; border-radius:10px 10px 10px 2px; align-self:flex-start; max-width:85%; font-family:sans-serif; font-size:14px;">Error connecting to local AI engine.</div>`;
        }
        
        messages.scrollTop = messages.scrollHeight;
        saveChatState(); 
    }

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
})();