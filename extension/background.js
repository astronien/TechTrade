// Background service worker
// ตรวจสอบและอัพเดท Session ID อัตโนมัติ

// ฟังการเปลี่ยนแปลง cookies
chrome.cookies.onChanged.addListener((changeInfo) => {
    if (changeInfo.cookie.name === 'ASP.NET_SessionId' && 
        changeInfo.cookie.domain.includes('eve.techswop.com')) {
        
        if (!changeInfo.removed) {
            // บันทึก Session ID ใหม่
            chrome.storage.local.set({
                sessionId: changeInfo.cookie.value,
                lastUpdate: new Date().toISOString()
            });
            
            console.log('✅ Session ID อัพเดทอัตโนมัติ:', changeInfo.cookie.value);
            
            // แจ้งเตือนผู้ใช้ (ถ้าต้องการ)
            chrome.notifications.create({
                type: 'basic',
                iconUrl: 'icon48.png',
                title: 'Session ID อัพเดทแล้ว',
                message: 'ระบบได้บันทึก Session ID ใหม่อัตโนมัติ'
            });
        }
    }
});

// ตรวจสอบ Session ID เมื่อเปิด Extension
chrome.runtime.onInstalled.addListener(() => {
    console.log('Trade-In Session Helper ติดตั้งเรียบร้อย');
});
