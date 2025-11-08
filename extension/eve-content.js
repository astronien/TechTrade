// Content script สำหรับหน้า eve.techswop.com
// ดึง Session ID จาก cookies

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'getSessionId') {
        // ดึง Session ID จาก cookies
        const sessionId = getSessionIdFromCookie();
        sendResponse({sessionId: sessionId});
    }
    return true;
});

function getSessionIdFromCookie() {
    const match = document.cookie.match(/ASP\.NET_SessionId=([^;]+)/);
    return match ? match[1] : null;
}

// Auto-detect และบันทึก Session ID เมื่อโหลดหน้า
window.addEventListener('load', () => {
    const sessionId = getSessionIdFromCookie();
    if (sessionId) {
        // บันทึกลง storage
        chrome.storage.local.set({
            sessionId: sessionId,
            lastUpdate: new Date().toISOString()
        });
        console.log('✅ Session ID ถูกบันทึกอัตโนมัติ:', sessionId);
    }
});
