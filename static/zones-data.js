// ข้อมูล Zone (เริ่มต้นเป็น array ว่าง)
// Area Manager สามารถสร้าง Zone ผ่านหน้าเว็บได้

const ZONES_DATA = [];

// ฟังก์ชันช่วยเหลือ
const ZoneHelper = {
    // ดึงรายชื่อสาขาทั้งหมดใน Zone
    getBranchesByZone: function(zoneId) {
        const zone = ZONES_DATA.find(z => z.zone_id === zoneId);
        if (!zone) return [];
        
        // ดึงข้อมูลสาขาจาก BRANCHES_DATA
        if (typeof BRANCHES_DATA === 'undefined') return [];
        
        return BRANCHES_DATA.filter(branch => 
            zone.branch_ids.includes(branch.branch_id)
        );
    },
    
    // ดึง branch_ids ทั้งหมดใน Zone (สำหรับส่งไป API)
    getBranchIdsByZone: function(zoneId) {
        const zone = ZONES_DATA.find(z => z.zone_id === zoneId);
        return zone ? zone.branch_ids : [];
    },
    
    // ดึงข้อมูล Zone ทั้งหมด
    getAllZones: function() {
        return ZONES_DATA;
    },
    
    // หา Zone ที่สาขานั้นอยู่
    getZonesByBranch: function(branchId) {
        return ZONES_DATA.filter(zone => 
            zone.branch_ids.includes(parseInt(branchId))
        );
    }
};

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ZONES_DATA, ZoneHelper };
}
