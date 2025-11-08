let currentSessionId = null;

document.addEventListener('DOMContentLoaded', function() {
    checkSession();
    
    document.getElementById('getSession').addEventListener('click', getSessionId);
    document.getElementById('sendToApp').addEventListener('click', sendToApp);
});

async function checkSession() {
    const statusDiv = document.getElementById('status');
    const sessionInfo = document.getElementById('sessionInfo');
    
    try {
        // ลองดึงจาก storage ก่อน
        const result = await chrome.storage.local.get(['sessionId']);
        
        if (result.sessionId) {
            currentSessionId = result.sessionId;
            statusDiv.className = 'status success';
            statusDiv.textContent = '✅ พบ Session ID';
            sessionInfo.innerHTML = `<div class="session-id">${currentSessionId}</div>`;
            return;
        }
        
        // ถ้าไม่มีใน storage ลองดึงจาก cookies
        const cookies = await chrome.cookies.getAll({
            domain: 'eve.techswop.com',
            name: 'ASP.NET_SessionId'
        });
        
        if (cookies.length > 0) {
            currentSessionId = cookies[0].value;
            
            // บันทึกลง storage
            await chrome.storage.local.set({
                sessionId: currentSessionId,
                lastUpdate: new Date().toISOString()
            });
            
            statusDiv.className = 'status success';
            statusDiv.textContent = '✅ พบ Session ID';
            sessionInfo.innerHTML = `<div class="session-id">${currentSessionId}</div>`;
        } else {
            // ลองดึงจาก tab ที่เปิด eve.techswop.com
            const tabs = await chrome.tabs.query({url: 'https://eve.techswop.com/*'});
            
            if (tabs.length > 0) {
                // ส่งข้อความไปยัง content script
                try {
                    const response = await chrome.tabs.sendMessage(tabs[0].id, {action: 'getSessionId'});
                    if (response && response.sessionId) {
                        currentSessionId = response.sessionId;
                        
                        // บันทึกลง storage
                        await chrome.storage.local.set({
                            sessionId: currentSessionId,
                            lastUpdate: new Date().toISOString()
                        });
                        
                        statusDiv.className = 'status success';
                        statusDiv.textContent = '✅ พบ Session ID';
                        sessionInfo.innerHTML = `<div class="session-id">${currentSessionId}</div>`;
                        return;
                    }
                } catch (e) {
                    console.log('Cannot get session from tab:', e);
                }
            }
            
            statusDiv.className = 'status error';
            statusDiv.textContent = '❌ ไม่พบ Session ID - กรุณา login ที่ eve.techswop.com';
            sessionInfo.innerHTML = '<p style="font-size: 12px; color: #721c24;">💡 เปิดหน้า eve.techswop.com และ login แล้วกดดึงข้อมูลอีกครั้ง</p>';
        }
    } catch (error) {
        statusDiv.className = 'status error';
        statusDiv.textContent = '❌ เกิดข้อผิดพลาด: ' + error.message;
    }
}

async function getSessionId() {
    const button = document.getElementById('getSession');
    button.disabled = true;
    button.textContent = '⏳ กำลังดึงข้อมูล...';
    
    await checkSession();
    
    button.disabled = false;
    button.textContent = '🔄 ดึง Session ID';
}

async function sendToApp() {
    const button = document.getElementById('sendToApp');
    const statusDiv = document.getElementById('status');
    
    if (!currentSessionId) {
        statusDiv.className = 'status error';
        statusDiv.textContent = '❌ ไม่มี Session ID - กรุณาดึงข้อมูลก่อน';
        return;
    }
    
    button.disabled = true;
    button.textContent = '⏳ กำลังส่ง...';
    
    try {
        // ส่งข้อความไปยัง content script
        const tabs = await chrome.tabs.query({active: true, currentWindow: true});
        
        if (tabs.length > 0) {
            await chrome.tabs.sendMessage(tabs[0].id, {
                action: 'setSessionId',
                sessionId: currentSessionId
            });
            
            statusDiv.className = 'status success';
            statusDiv.textContent = '✅ ส่ง Session ID สำเร็จ!';
        } else {
            // ถ้าไม่มี tab ที่เปิดอยู่ ให้เปิดหน้าระบบ
            chrome.tabs.create({
                url: 'http://localhost:5000'
            });
            
            statusDiv.className = 'status info';
            statusDiv.textContent = '📂 เปิดหน้าระบบแล้ว - กรุณากดส่งอีกครั้ง';
        }
    } catch (error) {
        statusDiv.className = 'status error';
        statusDiv.textContent = '❌ ส่งไม่สำเร็จ: ' + error.message;
    } finally {
        button.disabled = false;
        button.textContent = '📤 ส่งไปยังระบบ';
    }
}
