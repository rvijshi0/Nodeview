// ═══════════════════════════════════════════════════════════════════
// NodeView — Enterprise Frontend Application Controller
// Premium Dashboard with Real-time Topology, Troubleshooting,
// Agent Management, Network Config, and Downloads
// ═══════════════════════════════════════════════════════════════════

let cy = null;
let troubleshootCy = null;
let uiSocket = null;
let currentTab = "summary";
let token = localStorage.getItem("admin_token");
let agentsList = [];
let networkList = [];
let autoRefreshInterval = null;

// ── Custom SVG Badge Icons for Network Architecture nodes ───────
const svgToDataUri = (svg) => 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);

const DEVICE_SVGS = {
    internet: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="cloudGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#3b82f6"/><stop offset="100%" stop-color="#06b6d4"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#3b82f6" stroke-width="2.5"/><path d="M44 35.5h-2.1c-1.1-5.1-5.6-9-10.9-9-4.8 0-8.9 3.2-10.4 7.6-3.8.4-6.6 3.6-6.6 7.4 0 4.1 3.4 7.5 7.5 7.5h22.5c5 0 9-4 9-9s-4-9-9-9z" fill="url(#cloudGrad)"/></svg>`),
    firewall: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="firewallGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#ef4444"/><stop offset="100%" stop-color="#b91c1c"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#f43f5e" stroke-width="2.5"/><path d="M32 16l-12 5v10c0 7.4 5.1 14.3 12 16 6.9-1.7 12-8.6 12-16v-10l-12-5z" fill="url(#firewallGrad)"/><path d="M24 25h16M24 31h16M32 21v21" stroke="#ffffff" stroke-width="1.5" opacity="0.8"/></svg>`),
    switch: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="switchGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#06b6d4"/><stop offset="100%" stop-color="#0891b2"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#06b6d4" stroke-width="2.5"/><rect x="16" y="24" width="32" height="16" rx="2" fill="url(#switchGrad)"/><circle cx="22" cy="32" r="1.5" fill="#ffffff"/><circle cx="28" cy="32" r="1.5" fill="#ffffff"/><circle cx="34" cy="32" r="1.5" fill="#ffffff"/><circle cx="40" cy="32" r="1.5" fill="#ffffff"/><path d="M18 36h28" stroke="#ffffff" stroke-width="1" opacity="0.5"/></svg>`),
    router: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="routerGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#f59e0b"/><stop offset="100%" stop-color="#d97706"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#f59e0b" stroke-width="2.5"/><circle cx="32" cy="32" r="15" fill="url(#routerGrad)"/><path d="M32 20v24M20 32h24M24 24l16 16M24 40l16-16" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/></svg>`),
    ap: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="apGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#a855f7"/><stop offset="100%" stop-color="#7e22ce"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#a855f7" stroke-width="2.5"/><circle cx="32" cy="38" r="4" fill="#ffffff"/><path d="M26 30a10 10 0 0 1 12 0M20 24a18 18 0 0 1 24 0M32 16v18" stroke="url(#apGrad)" stroke-width="2.5" stroke-linecap="round" fill="none"/></svg>`),
    wlc: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="wlcGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#ec4899"/><stop offset="100%" stop-color="#be185d"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#ec4899" stroke-width="2.5"/><rect x="16" y="20" width="32" height="24" rx="2" fill="url(#wlcGrad)"/><path d="M20 26h24M20 32h24" stroke="#ffffff" stroke-width="1.5" opacity="0.8"/><circle cx="32" cy="38" r="2" fill="#ffffff"/></svg>`),
    agent: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="agentGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#047857"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#10b981" stroke-width="2.5"/><rect x="16" y="20" width="32" height="20" rx="2" fill="url(#agentGrad)"/><path d="M20 30h5l3-6 4 10 3-4h5" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/><path d="M26 44h12M32 40v4" stroke="#10b981" stroke-width="2" stroke-linecap="round"/></svg>`),
    laptop: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="laptopGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#3b82f6"/><stop offset="100%" stop-color="#1d4ed8"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#3b82f6" stroke-width="2.5"/><rect x="18" y="22" width="28" height="16" rx="1.5" fill="url(#laptopGrad)"/><path d="M14 38h36l2 4H12z" fill="#64748b"/><rect x="22" y="25" width="20" height="10" fill="#0f172a"/></svg>`),
    mobile: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="mobileGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#f59e0b"/><stop offset="100%" stop-color="#d97706"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#f59e0b" stroke-width="2.5"/><rect x="22" y="16" width="20" height="32" rx="3" fill="url(#mobileGrad)"/><rect x="24" y="20" width="16" height="24" fill="#0f172a"/><circle cx="32" cy="46" r="1.5" fill="#ffffff"/></svg>`),
    desktop: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="desktopGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#60a5fa"/><stop offset="100%" stop-color="#2563eb"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#60a5fa" stroke-width="2.5"/><rect x="18" y="20" width="28" height="18" rx="2" fill="url(#desktopGrad)"/><rect x="20" y="22" width="24" height="14" fill="#0f172a"/><path d="M28 42h8M32 38v4" stroke="#60a5fa" stroke-width="2.5" stroke-linecap="round"/></svg>`),
    iot: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="iotGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#ec4899"/><stop offset="100%" stop-color="#a855f7"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#ec4899" stroke-width="2.5"/><rect x="22" y="22" width="20" height="20" rx="2" fill="url(#iotGrad)"/><rect x="26" y="26" width="12" height="12" fill="#0f172a"/><path d="M32 16v6M32 42v6M16 32h6M42 32h6" stroke="#ec4899" stroke-width="2" stroke-linecap="round"/></svg>`),
    server: svgToDataUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="serverGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#6366f1"/><stop offset="100%" stop-color="#4f46e5"/></linearGradient></defs><circle cx="32" cy="32" r="28" fill="#0f172a" stroke="#6366f1" stroke-width="2.5"/><rect x="18" y="16" width="28" height="10" rx="1" fill="url(#serverGrad)"/><rect x="18" y="28" width="28" height="10" rx="1" fill="url(#serverGrad)"/><rect x="18" y="40" width="28" height="10" rx="1" fill="url(#serverGrad)"/><circle cx="22" cy="21" r="1.5" fill="#10b981"/><circle cx="22" cy="33" r="1.5" fill="#10b981"/><circle cx="22" cy="45" r="1.5" fill="#10b981"/><circle cx="26" cy="21" r="1.5" fill="#ffffff" opacity="0.8"/><circle cx="26" cy="33" r="1.5" fill="#ffffff" opacity="0.8"/><circle cx="26" cy="45" r="1.5" fill="#ffffff" opacity="0.8"/></svg>`)
};

// ── SVG Icon Helpers ──────────────────────────────────────────────
// Using inline SVGs for reliability (no CDN dependency for icons)
const ICONS = {
    activity: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>`,
    logo: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7L12 12L22 7L12 2Z"/><path d="M2 17L12 22L22 17"/><path d="M2 12L12 17L22 12"/></svg>`,
    server: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>`,
    shield: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`,
    monitor: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>`,
    smartphone: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"></rect><line x1="12" y1="18" x2="12.01" y2="18"></line></svg>`,
    cpu: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="14" x2="23" y2="14"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="14" x2="4" y2="14"></line></svg>`,
    wifi: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.55a11 11 0 0 1 14.08 0"></path><path d="M1.42 9a16 16 0 0 1 21.16 0"></path><path d="M8.53 16.11a6 6 0 0 1 6.95 0"></path><line x1="12" y1="20" x2="12.01" y2="20"></line></svg>`,
    globe: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>`,
    fingerprint: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12C2 6.5 6.5 2 12 2a10 10 0 0 1 8 4"></path><path d="M5 19.5C5.5 18 6 15 6 12c0-.7.12-1.37.34-2"></path><path d="M17.29 21.02c.12-.6.43-2.3.5-3.02"></path><path d="M12 10a2 2 0 0 0-2 2c0 1.02-.1 2.51-.26 4"></path><path d="M8.65 22c.21-.66.45-1.32.57-2"></path><path d="M14 13.12c0 2.38 0 6.38-1 8.88"></path><path d="M2 16h.01"></path><path d="M21.8 16c.2-2 .131-5.354 0-6"></path><path d="M9 6.8a6 6 0 0 1 9 5.2c0 .47 0 1.17-.02 2"></path></svg>`,
    play: `<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`,
    download: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>`,
    network: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="16" y="16" width="6" height="6" rx="1"></rect><rect x="2" y="16" width="6" height="6" rx="1"></rect><rect x="9" y="2" width="6" height="6" rx="1"></rect><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"></path><line x1="12" y1="12" x2="12" y2="8"></line></svg>`,
    zap: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>`,
    users: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>`,
    xCircle: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`,
    checkCircle: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`,
    clock: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>`,
    trash: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`,
    switchIcon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="10" rx="2"/><line x1="6" y1="12" x2="6.01" y2="12"/><line x1="10" y1="12" x2="10.01" y2="12"/><line x1="14" y1="12" x2="14.01" y2="12"/><line x1="18" y1="12" x2="18.01" y2="12"/></svg>`,
    radio: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2"></circle><path d="M16.24 7.76a6 6 0 0 1 0 8.49"></path><path d="M7.76 16.24a6 6 0 0 1 0-8.49"></path></svg>`,
    alertTriangle: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
    laptop: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 16V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v9m16 0H4m16 0 1.28 2.55a1 1 0 0 1-.9 1.45H3.62a1 1 0 0 1-.9-1.45L4 16"></path></svg>`,
    refreshCw: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>`,
    eye: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`,
    eyeOff: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`,
    settings: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>`
,
};

// ── Initialize Page ───────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    if (!token) {
        renderLoginPage();
    } else {
        renderDashboard();
    }
});

// ═══════════════════════════════════════════════════════════════════
// LOGIN PAGE
// ═══════════════════════════════════════════════════════════════════

function renderLoginPage() {
    document.body.innerHTML = `
        <div class="login-wrapper">
            <div class="login-card">
                <div class="login-header">
                    <div class="login-logo-icon">
                        ${ICONS.activity}
                    </div>
                    <h2>Node<span class="pro-tag">View</span> v1.5.1</h2>
                    <p>Your entire network, in single sight</p>
                </div>
                <div class="login-form">
                    <div class="form-group">
                        <label>Username</label>
                        <input type="text" id="login-username" placeholder="Enter username" autocomplete="username">
                    </div>
                    <div class="form-group" style="position: relative;">
                        <label>Password</label>
                        <input type="password" id="login-password" placeholder="Enter password" autocomplete="current-password">
                        <button type="button" id="toggle-password" style="position: absolute; right: 10px; bottom: 10px; background: none; border: none; color: var(--text-dim); cursor: pointer; padding: 2px;">${ICONS.eye}</button>
                    </div>
                    <div id="login-error" class="login-error-msg"></div>
                    <button class="btn btn-primary btn-block" id="btn-login" style="margin-top: 8px;">
                        ${ICONS.shield} Access Dashboard
                    </button>
                </div>
            </div>
        </div>
    `;

    document.getElementById("btn-login").addEventListener("click", handleLoginSubmit);
    document.getElementById("login-password").addEventListener("keydown", (e) => {
        if (e.key === "Enter") handleLoginSubmit();
    });
    document.getElementById("login-username").addEventListener("keydown", (e) => {
        if (e.key === "Enter") document.getElementById("login-password").focus();
    });

    // Password visibility toggle
    document.getElementById("toggle-password").addEventListener("click", () => {
        const pwInput = document.getElementById("login-password");
        const toggleBtn = document.getElementById("toggle-password");
        if (pwInput.type === "password") {
            pwInput.type = "text";
            toggleBtn.innerHTML = ICONS.eyeOff;
        } else {
            pwInput.type = "password";
            toggleBtn.innerHTML = ICONS.eye;
        }
    });
}

async function handleLoginSubmit() {
    const u = document.getElementById("login-username").value;
    const p = document.getElementById("login-password").value;
    const errDiv = document.getElementById("login-error");
    const btn = document.getElementById("btn-login");

    btn.innerHTML = `<span class="loading-spinner"></span> Authenticating...`;
    btn.disabled = true;

    try {
        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: u, password: p })
        });

        if (res.ok) {
            const data = await res.json();
            token = data.token;
            localStorage.setItem("admin_token", token);
            renderDashboard();
        } else {
            const err = await res.json();
            errDiv.innerText = err.detail || "Authentication Failed";
            btn.innerHTML = `${ICONS.shield} Access Dashboard`;
            btn.disabled = false;
        }
    } catch (e) {
        errDiv.innerText = "Error connecting to server. Check if the backend is running.";
        btn.innerHTML = `${ICONS.shield} Access Dashboard`;
        btn.disabled = false;
    }
}

// ═══════════════════════════════════════════════════════════════════
// DASHBOARD LAYOUT
// ═══════════════════════════════════════════════════════════════════

function renderDashboard() {
    document.body.innerHTML = `
        <div class="app-container">
            <!-- Sidebar -->
            <aside class="sidebar">
                <header class="sidebar-header">
                    <div class="logo">
                        ${ICONS.logo}
                        <span>Node<strong class="pro-tag">View</strong> v1.5.1</span>
                    </div>
                    <div class="system-status">
                        <span class="pulse-indicator"></span>
                        <span>LIVE</span>
                    </div>
                </header>

                <nav class="sidebar-nav">
                    <button class="nav-item active" data-tab="summary">
                        <span class="nav-icon">${ICONS.network}</span> Topology
                    </button>
                    <button class="nav-item" data-tab="troubleshoot">
                        <span class="nav-icon">${ICONS.zap}</span> Troubleshoot
                    </button>
                    <button class="nav-item" data-tab="agents">
                        <span class="nav-icon">${ICONS.monitor}</span> Agents
                    </button>
                    <button class="nav-item" data-tab="networks">
                        <span class="nav-icon">${ICONS.globe}</span> Networks
                    </button>
                    <button class="nav-item" data-tab="discovered_nodes">
                        <span class="nav-icon">${ICONS.users}</span> Discovered Nodes
                    </button>
                    <button class="nav-item" data-tab="downloads">
                        <span class="nav-icon">${ICONS.download}</span> Downloads
                    </button>
                    <button class="nav-item" data-tab="settings">
                        <span class="nav-icon">${ICONS.settings}</span> Settings
                    </button>
                </nav>

                <div class="sidebar-footer">
                    <button class="btn btn-danger btn-sm btn-block" id="btn-logout">Logout</button>
                </div>
            </aside>

            <!-- Main Content -->
            <main class="main-content">
                <div id="page-content" class="page-viewport"></div>
                <!-- Real-time Console -->
                <div class="console-container">
                    <div class="console-header">
                        <h3><span class="console-dot"></span> Ingestion Stream</h3>
                        <button class="btn btn-secondary btn-sm" id="btn-clear-console">Clear</button>
                    </div>
                    <div class="console-body" id="console-stream">
                        <div class="console-line info-line">[SYSTEM] Console session established. Awaiting telemetry...</div>
                    </div>
                </div>
            </main>
        </div>
    `;

    // Navigation bindings
    document.querySelectorAll(".nav-item").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const target = e.currentTarget;
            document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
            target.classList.add("active");
            switchTab(target.getAttribute("data-tab"));
        });
    });

    document.getElementById("btn-logout").addEventListener("click", () => {
        localStorage.removeItem("admin_token");
        token = null;
        if (autoRefreshInterval) clearInterval(autoRefreshInterval);
        renderLoginPage();
    });

    document.getElementById("btn-clear-console").addEventListener("click", () => {
        document.getElementById("console-stream").innerHTML = '<div class="console-line info-line">[SYSTEM] Console logs cleared.</div>';
    });

    switchTab("summary");
    setupWebSocket();
}

// ═══════════════════════════════════════════════════════════════════
// TAB ROUTER
// ═══════════════════════════════════════════════════════════════════

function switchTab(tabName) {
    currentTab = tabName;
    if (autoRefreshInterval) { clearInterval(autoRefreshInterval); autoRefreshInterval = null; }

    const viewport = document.getElementById("page-content");

    switch (tabName) {
        case "summary": renderSummaryTab(viewport); break;
        case "troubleshoot": renderTroubleshootTab(viewport); break;
        case "agents": renderAgentsTab(viewport); break;
        case "networks": renderNetworksTab(viewport); break;
        case "discovered_nodes": renderDiscoveredNodesTab(); break;
        case "downloads": renderDownloadsTab(viewport); break;
        case "settings": renderSettingsTab(viewport); break;
    }
}


// ═══════════════════════════════════════════════════════════════════
// TAB 1: SUMMARY / TOPOLOGY
// ═══════════════════════════════════════════════════════════════════

function renderSummaryTab(viewport) {
    viewport.innerHTML = `
        <div class="canvas-container">
            <div class="canvas-header">
                <h2>${ICONS.network} Network Topology</h2>
                <div class="canvas-actions">
                    <button class="btn btn-secondary btn-sm" id="btn-refresh-topology">${ICONS.refreshCw} Reload</button>
                </div>
            </div>
            <div id="cy" class="cytoscape-canvas"></div>

            <!-- Topology Legend -->
            <div class="topology-legend">
                <div class="legend-item"><span class="legend-dot" style="background: #f43f5e;"></span> Firewall</div>
                <div class="legend-item"><span class="legend-dot" style="background: #06b6d4;"></span> Switch</div>
                <div class="legend-item"><span class="legend-dot" style="background: #ec4899;"></span> WLC</div>
                <div class="legend-item"><span class="legend-dot" style="background: #a855f7;"></span> AP</div>
                <div class="legend-item"><span class="legend-dot" style="background: #10b981;"></span> Agent</div>
                <div class="legend-item"><span class="legend-dot" style="background: #3b82f6;"></span> Laptop</div>
                <div class="legend-item"><span class="legend-dot" style="background: #f59e0b;"></span> Mobile</div>
                <div class="legend-item"><span class="legend-dot" style="background: #e2e8f0; border: 1px solid #94a3b8;"></span> Grouped</div>
            </div>

            <!-- Node Inspector Drawer -->
            <div class="node-drawer-floating" id="node-drawer">
                <h4>Node Inspector</h4>
                <div id="node-drawer-body">
                    <div class="placeholder-text">Click a device to inspect details.</div>
                </div>
            </div>
        </div>
    `;

    initCytoscape();
    fetchTopology();
    document.getElementById("btn-refresh-topology").addEventListener("click", fetchTopology);
}

function initCytoscape() {
    cy = cytoscape({
        container: document.getElementById('cy'),
        style: [
            {
                selector: 'node',
                style: {
                    'content': 'data(label)',
                    'color': '#cbd5e1',
                    'font-family': 'Inter, sans-serif',
                    'font-size': '11px',
                    'font-weight': '600',
                    'text-valign': 'bottom',
                    'text-margin-y': '9px',
                    'text-outline-color': '#0a0e1a',
                    'text-outline-width': '2px',
                    'background-fit': 'contain',
                    'background-opacity': 0,
                    'width': '49px',
                    'height': '49px',
                    'overlay-padding': '7px',
                    'transition-property': 'width, height',
                    'transition-duration': '0.3s'
                }
            },
            {
                selector: 'node[type="internet"]',
                style: {
                    'background-image': DEVICE_SVGS.internet,
                    'width': '62px', 'height': '62px'
                }
            },
            {
                selector: 'node[type="firewall"]',
                style: {
                    'background-image': DEVICE_SVGS.firewall,
                    'width': '54px', 'height': '54px'
                }
            },
            {
                selector: 'node[type="switch"]',
                style: {
                    'background-image': DEVICE_SVGS.switch,
                    'width': '54px', 'height': '54px'
                }
            },
            {
                selector: 'node[type="router"]',
                style: {
                    'background-image': DEVICE_SVGS.router,
                    'width': '52px', 'height': '52px'
                }
            },
            {
                selector: 'node[type="ap"]',
                style: {
                    'background-image': DEVICE_SVGS.ap,
                    'width': '49px', 'height': '49px'
                }
            },
            {
                selector: 'node[type="wlc"]',
                style: {
                    'background-image': DEVICE_SVGS.wlc,
                    'width': '49px', 'height': '49px'
                }
            },
            {
                selector: 'node[type="agent"]',
                style: {
                    'background-image': DEVICE_SVGS.agent,
                    'width': '52px', 'height': '52px'
                }
            },
            {
                selector: 'node[type="laptop"]',
                style: {
                    'background-image': DEVICE_SVGS.laptop,
                    'width': '44px', 'height': '44px'
                }
            },
            {
                selector: 'node[type="mobile"]',
                style: {
                    'background-image': DEVICE_SVGS.mobile,
                    'width': '41px', 'height': '41px'
                }
            },
            {
                selector: 'node[type="desktop"]',
                style: {
                    'background-image': DEVICE_SVGS.desktop,
                    'width': '44px', 'height': '44px'
                }
            },
            {
                selector: 'node[type="iot"]',
                style: {
                    'background-image': DEVICE_SVGS.iot,
                    'width': '41px', 'height': '41px'
                }
            },
            {
                selector: 'node[type="server"]',
                style: {
                    'background-image': DEVICE_SVGS.server,
                    'width': '49px', 'height': '49px'
                }
            },
            {
                selector: 'node[type="collapsed_group"]',
                style: {
                    'background-color': 'rgba(99, 102, 241, 0.15)',
                    'background-opacity': 0.8,
                    'color': '#818cf8',
                    'border-color': '#6366f1',
                    'border-width': '2px',
                    'border-style': 'dashed',
                    'shape': 'ellipse',
                    'width': '54px',
                    'height': '54px',
                    'font-size': '15px',
                    'font-weight': '800',
                    'text-valign': 'center',
                    'text-margin-y': '0px'
                }
            },
            {
                selector: 'node:selected',
                style: {
                    'border-color': '#6366f1',
                    'border-width': '3px',
                    'shadow-blur': '15',
                    'shadow-color': 'rgba(99, 102, 241, 0.5)',
                    'shadow-opacity': 0.8
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 1.5,
                    'line-color': 'rgba(99, 102, 241, 0.15)',
                    'curve-style': 'bezier',
                    'target-arrow-shape': 'none',
                    'line-style': 'solid',
                    'opacity': 0.6
                }
            },
            {
                selector: 'edge:selected',
                style: {
                    'line-color': 'rgba(99, 102, 241, 0.5)',
                    'width': 2.5,
                    'opacity': 1
                }
            }
        ],
        layout: { name: 'preset' },
        wheelSensitivity: 0.3,
        minZoom: 0.3,
        maxZoom: 3
    });

    cy.on('tap', 'node', (evt) => {
        const data = evt.target.data();
        if (data.type === 'cluster_group') {
            document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
            const tabBtn = document.querySelector(".nav-item[data-tab='discovered_nodes']");
            if(tabBtn) tabBtn.classList.add("active");
            currentTab = 'discovered_nodes';
            renderDiscoveredNodesTab(data.groupList || []);
        } else {
            inspectNode(data);
        }
    });

    cy.on('tap', (evt) => {
        if (evt.target === cy) {
            const drawer = document.getElementById("node-drawer-body");
            if (drawer) drawer.innerHTML = '<div class="placeholder-text">Click a device to inspect details.</div>';
        }
    });
}

function computeHierarchicalCoordinates(elements) {
    const nodes = elements.nodes || [];
    const typeLevels = {
        'internet': 0,
        'firewall': 1,
        'router': 2,
        'switch': 3,
        'wlc': 3,
        'ap': 4,
        'agent': 5,
        'server': 5,
        'collapsed_group': 6,
        'laptop': 6,
        'desktop': 6,
        'mobile': 6,
        'iot': 6
    };

    const levels = {};
    nodes.forEach(node => {
        const type = node.data.type || 'laptop';
        const lvl = typeLevels[type] !== undefined ? typeLevels[type] : 6;
        if (!levels[lvl]) levels[lvl] = [];
        levels[lvl].push(node);
    });

    const canvasWidth = 1200;
    const levelHeight = 120;

    Object.keys(levels).forEach(lvlStr => {
        const lvl = parseInt(lvlStr);
        const group = levels[lvl];
        const count = group.length;
        const spacing = canvasWidth / (count + 1);

        group.forEach((node, idx) => {
            node.position = {
                x: spacing * (idx + 1),
                y: 60 + lvl * levelHeight
            };
        });
    });

    return elements;
}

async function fetchTopology() {
    try {
        const res = await fetch("/api/topology");
        if (!res.ok) throw new Error("Graph API error");
        const rawData = await res.json();
        let processedElements = processDeviceCollapsing(rawData);
        
        // Calculate coordinates based on tier level
        processedElements = computeHierarchicalCoordinates(processedElements);

        cy.json({ elements: processedElements });
        cy.layout({
            name: 'preset',
            animate: true,
            animationDuration: 400
        }).run();

        cy.fit(60);
    } catch (e) {
        logConsole(`Error loading topology: ${e.message}`, "error");
    }
}

/**
 * Enterprise Collapsing: When a parent (Switch/AP) has >5 children of same
 * type, collapse them into a single "Type (N)" group node.
 */
function processDeviceCollapsing(graphData) {
    const nodes = graphData.nodes || [];
    const edges = graphData.edges || [];
    const parentMap = {};

    edges.forEach(edge => {
        const src = edge.data.source;
        const tgt = edge.data.target;
        if (!parentMap[src]) parentMap[src] = [];
        parentMap[src].push(tgt);
    });

    const collapsedNodeIds = new Set();
    const finalNodes = [];
    const finalEdges = [];

    nodes.forEach(node => {
        const nid = node.data.id;
        const children = parentMap[nid] || [];

        const typeGroups = {};
        children.forEach(childId => {
            const childNode = nodes.find(n => n.data.id === childId);
            if (childNode && ["laptop", "desktop", "mobile", "iot"].includes(childNode.data.type)) {
                const dtype = childNode.data.type;
                if (!typeGroups[dtype]) typeGroups[dtype] = [];
                typeGroups[dtype].push(childNode);
            }
        });

        Object.keys(typeGroups).forEach(deviceType => {
            const groupList = typeGroups[deviceType];
            if (groupList.length > 5) {
                const groupNodeId = `collapsed_${nid}_${deviceType}`;
                finalNodes.push({
                    data: {
                        id: groupNodeId,
                        label: `${groupList.length}`,
                        type: 'collapsed_group',
                        details: groupList.map(n => `${n.data.label} (${n.data.ip || "N/A"})`).join(", "),
                        childType: deviceType,
                        count: groupList.length
                    }
                });
                finalEdges.push({
                    data: {
                        id: `edge_${nid}_to_${groupNodeId}`,
                        source: nid,
                        target: groupNodeId
                    }
                });
                groupList.forEach(child => collapsedNodeIds.add(child.data.id));
            }
        });
    });

    nodes.forEach(node => {
        if (!collapsedNodeIds.has(node.data.id)) {
            finalNodes.push(node);
        }
    });

    edges.forEach(edge => {
        if (!collapsedNodeIds.has(edge.data.source) && !collapsedNodeIds.has(edge.data.target)) {
            finalEdges.push(edge);
        }
    });

    return { nodes: finalNodes, edges: finalEdges };
}

function inspectNode(data) {
    const drawer = document.getElementById("node-drawer-body");
    if (!drawer) return;

    if (data.type === "collapsed_group") {
        drawer.innerHTML = `
            <div class="details-grid">
                <span class="details-label">Type</span>
                <span class="details-value"><span class="badge-device collapsed">Grouped ${data.childType || "devices"}</span></span>
                <span class="details-label">Count</span>
                <span class="details-value">${data.count || data.label} devices</span>
                <span class="details-label">Members</span>
                <span class="details-value" style="font-size: 0.7rem; color: var(--text-muted); line-height: 1.5;">${data.details || "N/A"}</span>
            </div>
        `;
        return;
    }

    drawer.innerHTML = `
        <div class="details-grid">
            <span class="details-label">Type</span>
            <span class="details-value"><span class="badge-device ${data.type}">${data.type}</span></span>
            <span class="details-label">Label</span>
            <span class="details-value">${data.label || "Unknown"}</span>
            <span class="details-label">IP</span>
            <span class="details-value" style="font-family: 'Fira Code', monospace; font-size: 0.78rem;">${data.ip || "N/A"}</span>
            <span class="details-label">MAC</span>
            <span class="details-value" style="font-family: 'Fira Code', monospace; font-size: 0.78rem;">${data.mac || "N/A"}</span>
        </div>
    `;
}

async function renderDiscoveredNodesTab(devices) {
    const viewport = document.getElementById("page-content");
    viewport.innerHTML = `<div style="padding:40px; text-align:center;">${ICONS.refreshCw} Loading devices...</div>`;
    
    if (devices === undefined) {
        try {
            const res = await fetch("/api/devices");
            devices = await res.json();
        } catch (e) {
            logConsole("Failed to fetch devices", "error");
            devices = [];
        }
    }

    let rows = "";
    if (devices && devices.length > 0) {
        devices.forEach(dev => {
            rows += `<tr>
                <td><span class="badge-device ${dev.type}">${dev.type}</span></td>
                <td>${dev.label}</td>
                <td style="font-family: 'Fira Code', monospace; font-size: 0.85rem;">${dev.ip || "N/A"}</td>
                <td style="font-family: 'Fira Code', monospace; font-size: 0.85rem;">${dev.mac || "N/A"}</td>
                <td><span class="pro-tag">${dev.discovered_by || "Unknown"}</span></td>
            </tr>`;
        });
    } else {
        rows = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim);">No devices clustered or discovered yet.</td></tr>`;
    }

    viewport.innerHTML = `
        <div class="card" style="margin: 20px;">
            <div class="card-header">
                <h3>${ICONS.users} Discovered Nodes</h3>
                <p class="card-subtitle">List of peripheral devices discovered by agents on their local VLANs.</p>
            </div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th class="resizable-th">Device Type</th>
                            <th class="resizable-th">Hostname / Label</th>
                            <th class="resizable-th">IP Address</th>
                            <th class="resizable-th">MAC Address</th>
                            <th class="resizable-th">Discovered By</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// ═══════════════════════════════════════════════════════════════════
// TAB 2: TROUBLESHOOT

// ═══════════════════════════════════════════════════════════════════

function renderTroubleshootTab(viewport) {
    viewport.innerHTML = `
        <div class="troubleshoot-layout">
            <!-- Left: Controls Sidebar -->
            <div class="troubleshoot-sidebar">
                <h3>${ICONS.zap} Troubleshoot</h3>
                <p class="card-subtitle">Cross-VLAN connectivity testing with collaborative packet injection and spoofing capabilities.</p>

                <div class="form-group">
                    <label>Source Agent (Injector)</label>
                    <select id="diag-src-agent">
                        <option value="">Loading agents...</option>
                    </select>
                </div>

                <div class="form-group">
                    <label>Destination IP</label>
                    <input type="text" id="diag-target-ip" placeholder="e.g. 10.0.20.10">
                </div>

                <div class="form-group">
                    <label>Protocol / Port</label>
                    <select id="diag-protocol">
                        <option value="icmp">ICMP (Ping)</option>
                        <option value="tcp" selected>TCP</option>
                        <option value="udp">UDP</option>
                        <option value="traceroute">Traceroute (tracert)</option>
                    </select>
                </div>

                <div class="form-group">
                    <label>Port Number</label>
                    <input type="number" id="diag-target-port" value="443" min="1" max="65535">
                </div>

                <!-- IP Spoofing Section -->
                <div class="spoof-section">
                    <div class="spoof-toggle">
                        <input type="checkbox" id="spoof-ip-toggle">
                        <label for="spoof-ip-toggle">${ICONS.globe} Spoof Source IP</label>
                    </div>
                    <div class="spoof-fields hidden" id="spoof-ip-fields">
                        <input type="text" id="spoof-ip-value" placeholder="Unmanaged IP (e.g. 10.0.10.99)">
                    </div>

                    <div class="spoof-toggle" style="margin-top: 10px;">
                        <input type="checkbox" id="spoof-mac-toggle">
                        <label for="spoof-mac-toggle">${ICONS.fingerprint} Spoof Source MAC</label>
                    </div>
                    <div class="spoof-fields hidden" id="spoof-mac-fields">
                        <input type="text" class="mac-input" id="spoof-mac-value" placeholder="Fake MAC (e.g. AA:BB:CC:DD:EE:FF)">
                    </div>

                    <div id="spoof-hint-box"></div>
                </div>

                <button class="btn btn-primary btn-block" id="btn-run-diag" style="margin-top: 6px;">
                    ${ICONS.play} Initialize Test
                </button>
            </div>

            <!-- Right: Live Trace Canvas + Output -->
            <div class="troubleshoot-canvas">
                <div class="troubleshoot-canvas-area" id="troubleshoot-cy-container">
                    <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-dim); font-size: 0.82rem;">
                        <div class="empty-state">
                            ${ICONS.network}
                            <p>Configure and run a test to see live network trace visualization.</p>
                        </div>
                    </div>
                </div>
                <div class="trace-output" id="trace-output">
                    <div class="trace-line info-msg">[SYSTEM] Awaiting test initialization...</div>
                </div>
            </div>
        </div>
    `;

    populateDiagAgents();
    bindTroubleshootEvents();
}

function bindTroubleshootEvents() {
    // IP Spoofing toggle
    document.getElementById("spoof-ip-toggle").addEventListener("change", (e) => {
        document.getElementById("spoof-ip-fields").classList.toggle("hidden", !e.target.checked);
        if (!e.target.checked) {
            document.getElementById("spoof-mac-toggle").checked = false;
            document.getElementById("spoof-mac-fields").classList.add("hidden");
        }
        updateSpoofHint();
    });

    // MAC Spoofing toggle
    document.getElementById("spoof-mac-toggle").addEventListener("change", (e) => {
        document.getElementById("spoof-mac-fields").classList.toggle("hidden", !e.target.checked);
        if (e.target.checked && !document.getElementById("spoof-ip-toggle").checked) {
            document.getElementById("spoof-ip-toggle").checked = true;
            document.getElementById("spoof-ip-fields").classList.remove("hidden");
        }
        updateSpoofHint();
    });

    document.getElementById("btn-run-diag").addEventListener("click", runAdvancedDiagnostic);
}

function updateSpoofHint() {
    const hintBox = document.getElementById("spoof-hint-box");
    const spoofEnabled = document.getElementById("spoof-ip-toggle").checked;

    if (!spoofEnabled) {
        hintBox.innerHTML = '';
        return;
    }

    // Check if target IP has an agent
    const targetIp = document.getElementById("diag-target-ip").value;
    const targetAgent = agentsList.find(a => a.ip_address === targetIp && a.status === "online");

    if (targetAgent) {
        hintBox.innerHTML = `
            <div class="spoof-hint collaborative">
                ${ICONS.radio} <span><strong>Collaborative Mode:</strong> Target agent "${targetAgent.name}" will listen for the spoofed packet and report reception.</span>
            </div>`;
    } else {
        hintBox.innerHTML = `
            <div class="spoof-hint blind">
                ${ICONS.alertTriangle} <span><strong>Blind Mode:</strong> No agent at target. Replies may be lost. Use a destination with an active agent for collaborative verification.</span>
            </div>`;
    }
}

async function populateDiagAgents() {
    const select = document.getElementById("diag-src-agent");
    try {
        const res = await fetch("/api/agents");
        if (res.ok) {
            const agents = await res.json();
            agentsList = agents;
            select.innerHTML = `<option value="">Select source agent...</option>`;
            agents.forEach(a => {
                if (a.status === "online") {
                    select.innerHTML += `<option value="${a.id}">${a.name} (${a.ip_address})</option>`;
                } else {
                    select.innerHTML += `<option value="${a.id}" disabled style="color: var(--text-dim);">${a.name} — Offline</option>`;
                }
            });
        }
    } catch (e) {
        select.innerHTML = `<option value="">Error loading agents</option>`;
    }
}

async function runAdvancedDiagnostic() {
    const srcId = document.getElementById("diag-src-agent").value;
    const ip = document.getElementById("diag-target-ip").value;
    const port = document.getElementById("diag-target-port").value;
    const protocol = document.getElementById("diag-protocol").value;
    const spoofIp = document.getElementById("spoof-ip-toggle").checked ? document.getElementById("spoof-ip-value").value : null;
    const spoofMac = document.getElementById("spoof-mac-toggle").checked ? document.getElementById("spoof-mac-value").value : null;

    if (!srcId || !ip || !port) {
        traceLog("Missing required fields: Select agent, enter destination IP and port.", "error-msg");
        return;
    }

    const btn = document.getElementById("btn-run-diag");
    btn.disabled = true;
    btn.innerHTML = `<span class="loading-spinner"></span> Executing...`;

    const traceOutput = document.getElementById("trace-output");
    traceOutput.innerHTML = '';

    traceLog(`[SERVER] Initializing diagnostic test sequence...`, "server-msg");

    // Build payload
    const payload = {
        source_agent_id: parseInt(srcId),
        target_ip: ip,
        target_port: parseInt(port),
        protocol: protocol
    };

    if (spoofIp) payload.spoof_ip = spoofIp;
    if (spoofMac) payload.spoof_mac = spoofMac;

    try {
        // Try advanced endpoint first, fallback to basic
        let res;
        try {
            res = await fetch("/api/diagnostics/advanced", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
        } catch (e) {
            // Fallback to basic endpoint
            res = await fetch("/api/diagnostics/test", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
        }

        if (res.ok) {
            const data = await res.json();
            traceLog(`[SERVER] Test initiated. ID: ${data.test_id || 'N/A'}`, "server-msg");

            if (spoofIp) {
                const srcAgent = agentsList.find(a => a.id == srcId);
                traceLog(`[${srcAgent?.name || 'Agent'}] Preparing packet: SRC_IP=${spoofIp} → DST=${ip}:${port}`, "agent-msg");
            }

            traceLog(`[SERVER] Awaiting agent response. Results will stream in real-time...`, "info-msg");
        } else {
            const errData = await res.json();
            traceLog(`[ERROR] ${errData.detail || 'Test failed'}`, "error-msg");
        }
    } catch (e) {
        traceLog(`[ERROR] Failed to initiate: ${e.message}`, "error-msg");
    }

    btn.disabled = false;
    btn.innerHTML = `${ICONS.play} Initialize Test`;
}

function traceLog(message, className = "info-msg") {
    const container = document.getElementById("trace-output");
    if (!container) return;

    const line = document.createElement("div");
    line.className = `trace-line ${className}`;
    const time = new Date().toLocaleTimeString();
    line.innerText = `[${time}] ${message}`;
    container.appendChild(line);
    container.scrollTop = container.scrollHeight;
}

// ═══════════════════════════════════════════════════════════════════
// TAB 3: AGENT INVENTORY
// ═══════════════════════════════════════════════════════════════════

function renderAgentsTab(viewport) {
    viewport.innerHTML = `
        <div>
            <div class="agents-header">
                <h3>${ICONS.monitor} Agent Inventory</h3>
                <span class="agents-count" id="agents-count">Loading...</span>
            </div>
            <div class="agent-grid" id="agents-grid">
                <div class="empty-state" style="grid-column: 1/-1;">
                    <p>Loading agent inventory...</p>
                </div>
            </div>
        </div>
    `;

    loadAgentsGrid();

    // Auto-refresh every 10 seconds
    autoRefreshInterval = setInterval(() => {
        if (currentTab === "agents") loadAgentsGrid();
    }, 10000);
}

async function loadAgentsGrid() {
    const grid = document.getElementById("agents-grid");
    const countBadge = document.getElementById("agents-count");

    try {
        const res = await fetch("/api/agents");
        if (res.ok) {
            const agents = await res.json();
            agentsList = agents;

            const online = agents.filter(a => a.status === "online").length;
            if (countBadge) countBadge.textContent = `${online} online / ${agents.length} total`;

            if (agents.length === 0) {
                grid.innerHTML = `
                    <div class="empty-state" style="grid-column: 1/-1;">
                        ${ICONS.monitor}
                        <p>No agents registered. Deploy agents using the Downloads page.</p>
                    </div>`;
                return;
            }

            grid.innerHTML = agents.map((a, i) => `
                <div class="agent-card ${a.status === 'offline' ? 'offline' : ''}" style="animation-delay: ${i * 0.05}s;">
                    <div class="agent-card-header">
                        <div class="agent-card-name">
                            <div class="agent-card-icon">${ICONS.monitor}</div>
                            <span>${a.name}</span>
                        </div>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <span class="status-pill ${a.status}">${a.status}</span>
                            <button class="btn btn-secondary btn-sm" onclick="openEditAgentModal(${a.id}, '${a.name}', '${a.ip_address || ''}', '${a.mac_address || ''}')" title="Edit Agent IP/MAC" style="padding: 2px 6px; font-size: 0.75rem;">
                                ✏️
                            </button>
                        </div>
                    </div>
                    <div class="agent-card-details">
                        <span class="agent-detail-label">IP Address</span>
                        <span class="agent-detail-value">${a.ip_address || "N/A"}</span>
                        <span class="agent-detail-label">MAC</span>
                        <span class="agent-detail-value">${a.mac_address || "N/A"}</span>
                        <span class="agent-detail-label">Last Seen</span>
                        <span class="agent-detail-value" style="font-family: Inter, sans-serif; font-size: 0.7rem; color: var(--text-muted);">
                            ${a.last_seen ? new Date(a.last_seen).toLocaleString() : "Never"}
                        </span>
                    </div>
                </div>
            `).join("");
        }
    } catch (e) {
        grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;"><p style="color: var(--danger);">Error loading agents: ${e.message}</p></div>`;
    }
}

// ═══════════════════════════════════════════════════════════════════
// TAB 4: NETWORK CONFIGURATION
// ═══════════════════════════════════════════════════════════════════

function renderNetworksTab(viewport) {
    viewport.innerHTML = `
        <div class="networks-layout">
            <div class="card">
                <h3>${ICONS.globe} Define Network / VLAN Range</h3>
                <p class="card-subtitle">Configure IP ranges for agent-based peer scanning. Agents auto-match their subnet and scan at the defined frequency.</p>
                <div class="form-grid">
                    <div class="form-group">
                        <label>Network Name</label>
                        <input type="text" id="net-name" placeholder="e.g., VLAN-10-Corporate">
                    </div>
                    <div class="form-group">
                        <label>CIDR Range</label>
                        <input type="text" id="net-cidr" placeholder="e.g., 10.0.10.0/24">
                    </div>
                    <div class="form-group">
                        <label>Scan Frequency (seconds)</label>
                        <input type="number" id="net-freq" value="60" min="10" max="3600">
                    </div>
                </div>
                <button class="btn btn-primary" id="btn-save-net" style="margin-top: 18px;">
                    Save Network Definition
                </button>
            </div>

            <div>
                <h3 style="font-family: 'Outfit', sans-serif; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
                    ${ICONS.network} Configured Ranges
                </h3>
                <div class="network-card-grid" id="networks-grid">
                    <div class="empty-state"><p>Loading networks...</p></div>
                </div>
            </div>

            <div class="card" style="margin-top: 28px;">
                <h3>${ICONS.globe} Define Internet IP Target</h3>
                <p class="card-subtitle">Specify public IP addresses for agents to traceroute periodically. This automatically maps network path breakouts and common firewalls/routers.</p>
                <div class="form-grid">
                    <div class="form-group">
                        <label>Internet IP Address</label>
                        <input type="text" id="target-ip-addr" placeholder="e.g., 8.8.8.8">
                    </div>
                    <div class="form-group">
                        <label>Description / Name</label>
                        <input type="text" id="target-ip-desc" placeholder="e.g., Google DNS">
                    </div>
                </div>
                <button class="btn btn-primary" id="btn-save-target" style="margin-top: 18px;">
                    Save Internet Target
                </button>
            </div>

            <div>
                <h3 style="font-family: 'Outfit', sans-serif; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
                    ${ICONS.globe} Configured Internet Targets
                </h3>
                <div class="network-card-grid" id="targets-grid">
                    <div class="empty-state"><p>Loading internet targets...</p></div>
                </div>
            </div>
        </div>
    `;

    loadNetworksGrid();
    loadInternetTargetsGrid();
    document.getElementById("btn-save-net").addEventListener("click", saveSubnetConfig);
    document.getElementById("btn-save-target").addEventListener("click", saveInternetTarget);
}

async function loadNetworksGrid() {
    const grid = document.getElementById("networks-grid");

    try {
        const res = await fetch("/api/networks");
        if (res.ok) {
            const nets = await res.json();
            networkList = nets;

            if (nets.length === 0) {
                grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;"><p>No network ranges defined yet.</p></div>`;
                return;
            }

            grid.innerHTML = nets.map((n, i) => `
                <div class="network-card" style="animation-delay: ${i * 0.05}s;">
                    <div class="network-card-header">
                        <div class="network-card-name">
                            ${ICONS.globe}
                            <span>${n.name}</span>
                        </div>
                        <button class="btn btn-danger btn-sm" onclick="deleteSubnetConfig(${n.id})" title="Delete">
                            ${ICONS.trash}
                        </button>
                    </div>
                    <div class="network-card-cidr">${n.cidr_range}</div>
                    <div class="network-card-freq">
                        ${ICONS.clock} Scan every <strong>${n.scan_frequency_seconds}s</strong>
                    </div>
                </div>
            `).join("");
        }
    } catch (e) {
        grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;"><p style="color: var(--danger);">Error loading networks.</p></div>`;
    }
}

async function saveSubnetConfig() {
    const name = document.getElementById("net-name").value;
    const cidr = document.getElementById("net-cidr").value;
    const freq = document.getElementById("net-freq").value;

    if (!name || !cidr) {
        logConsole("Enter network name and CIDR range.", "warning");
        return;
    }

    // Basic CIDR validation
    const cidrRegex = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\/\d{1,2}$/;
    if (!cidrRegex.test(cidr)) {
        logConsole("Invalid CIDR format. Use format: x.x.x.x/xx", "error");
        return;
    }

    try {
        const res = await fetch("/api/networks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, cidr_range: cidr, scan_frequency_seconds: parseInt(freq) })
        });
        if (res.ok) {
            loadNetworksGrid();
            document.getElementById("net-name").value = "";
            document.getElementById("net-cidr").value = "";
            logConsole(`Network "${name}" (${cidr}) configured successfully.`, "success");
        }
    } catch (e) {
        logConsole(`Error saving network: ${e.message}`, "error");
    }
}

async function deleteSubnetConfig(id) {
    if (!confirm("Remove this network definition?")) return;

    try {
        const res = await fetch(`/api/networks/${id}`, { method: "DELETE" });
        if (res.ok) {
            loadNetworksGrid();
            logConsole("Network definition removed.", "success");
        }
    } catch (e) {
        logConsole(`Delete error: ${e.message}`, "error");
    }
}

async function loadInternetTargetsGrid() {
    const grid = document.getElementById("targets-grid");
    try {
        const res = await fetch("/api/internet-targets");
        if (res.ok) {
            const targets = await res.json();
            if (targets.length === 0) {
                grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;"><p>No internet IP targets configured yet.</p></div>`;
                return;
            }

            grid.innerHTML = targets.map((t, i) => `
                <div class="network-card" style="animation-delay: ${i * 0.05}s;">
                    <div class="network-card-header">
                        <div class="network-card-name">
                            ${ICONS.globe}
                            <span>${t.description || t.ip_address}</span>
                        </div>
                        <button class="btn btn-danger btn-sm" onclick="deleteInternetTarget(${t.id})" title="Delete">
                            ${ICONS.trash}
                        </button>
                    </div>
                    <div class="network-card-cidr">${t.ip_address}</div>
                    <div class="network-card-freq">
                        ${ICONS.clock} Traceroute periodically configured
                    </div>
                </div>
            `).join("");
        }
    } catch (e) {
        grid.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;"><p style="color: var(--danger);">Error loading internet targets.</p></div>`;
    }
}

async function saveInternetTarget() {
    const ip = document.getElementById("target-ip-addr").value;
    const desc = document.getElementById("target-ip-desc").value;

    if (!ip) {
        logConsole("Enter target IP address.", "warning");
        return;
    }

    try {
        const res = await fetch("/api/internet-targets", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ip_address: ip, description: desc })
        });
        if (res.ok) {
            loadInternetTargetsGrid();
            document.getElementById("target-ip-addr").value = "";
            document.getElementById("target-ip-desc").value = "";
            logConsole(`Internet target "${ip}" configured successfully.`, "success");
            fetchTopology(); // Refresh layout to show internet node
        }
    } catch (e) {
        logConsole(`Error saving internet target: ${e.message}`, "error");
    }
}

async function deleteInternetTarget(id) {
    if (!confirm("Remove this internet target?")) return;

    try {
        const res = await fetch(`/api/internet-targets/${id}`, { method: "DELETE" });
        if (res.ok) {
            loadInternetTargetsGrid();
            logConsole("Internet target removed.", "success");
            fetchTopology(); // Refresh layout
        }
    } catch (e) {
        logConsole(`Delete error: ${e.message}`, "error");
    }
}

// ═══════════════════════════════════════════════════════════════════
// TAB 5: DOWNLOADS
// ═══════════════════════════════════════════════════════════════════

function renderDownloadsTab(viewport) {
    viewport.innerHTML = `
        <div class="downloads-layout">
            <div class="card">
                <h3>${ICONS.download} Agent Package Download</h3>
                <p class="card-subtitle">Configure the server connection details below. The system will generate a pre-configured agent package for deployment to Windows endpoints.</p>

                <div class="form-grid">
                    <div class="form-group">
                        <label>Server IP / URL</label>
                        <input type="text" id="dl-ip" value="${window.location.hostname}" placeholder="e.g., 192.168.1.100">
                    </div>
                    <div class="form-group">
                        <label>Server Port</label>
                        <input type="number" id="dl-port" value="${window.location.port || '8000'}">
                    </div>
                    <div class="form-group">
                        <label>Registration Password</label>
                        <input type="password" id="dl-password" placeholder="Leave empty for no password">
                    </div>
                </div>

                <button class="btn btn-primary" id="btn-build-download" style="margin-top: 18px;">
                    ${ICONS.download} Generate Agent Package
                </button>

                <div id="download-action-box" class="download-success-box hidden" style="margin-top: 20px;">
                    <h4>${ICONS.checkCircle} Package Ready</h4>
                    <p style="font-size: 0.78rem; color: var(--text-secondary); margin: 8px 0;">
                        Your pre-configured agent package is ready for download. Deploy to Windows endpoints to begin monitoring.
                    </p>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <a id="btn-dl-config" class="btn btn-secondary btn-sm" href="#" download>⬇️ Download config.json</a>
                        <a id="btn-dl-exe" class="btn btn-success btn-sm" href="/NodeViewAgent.exe" download>⬇️ Download Agent (.exe)</a>
                    </div>

                    <div class="install-instructions" style="margin-top: 16px;">
                        <h4>Installation Steps</h4>
                        <code>1. Place both files in the same directory</code>
                        <code>2. Run as Administrator:</code>
                        <code style="color: var(--success);">   NodeViewAgent.exe install</code>
                        <code>3. Start the service:</code>
                        <code style="color: var(--success);">   net start NodeViewAgent</code>
                        <code style="margin-top: 6px; color: var(--text-dim);">Or run standalone: python agent.py --server http://&lt;ip&gt;:&lt;port&gt;</code>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.getElementById("btn-build-download").addEventListener("click", generateAgentPackage);
}

async function generateAgentPackage() {
    const ip = document.getElementById("dl-ip").value;
    const port = document.getElementById("dl-port").value;
    const password = document.getElementById("dl-password").value;
    const box = document.getElementById("download-action-box");
    const configLink = document.getElementById("btn-dl-config");

    if (!ip || !port) {
        logConsole("Enter server IP and port.", "warning");
        return;
    }

    try {
        const res = await fetch("/api/downloads/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ip, port, password })
        });

        if (res.ok) {
            const data = await res.json();

            // Create downloadable config blob
            const blob = new Blob([data.config_content], { type: "application/json" });
            configLink.href = URL.createObjectURL(blob);
            configLink.download = data.config_filename;

            box.classList.remove("hidden");
            logConsole(`Agent package generated for ${ip}:${port}`, "success");
        }
    } catch (e) {
        logConsole(`Download generation failed: ${e.message}`, "error");
    }
}

// ═══════════════════════════════════════════════════════════════════
// WEBSOCKET TELEMETRY STREAM
// ═══════════════════════════════════════════════════════════════════

function setupWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/ui`;

    uiSocket = new WebSocket(wsUrl);

    uiSocket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        logConsole(payload.message, payload.type);

        // Also log to troubleshoot trace output if active
        if (currentTab === "troubleshoot") {
            const traceContainer = document.getElementById("trace-output");
            if (traceContainer) {
                let traceClass = "info-msg";
                if (payload.type === "success") traceClass = "success-msg";
                else if (payload.type === "warning") traceClass = "warning-msg";
                else if (payload.type === "error") traceClass = "error-msg";
                else if (payload.message.includes("Diagnostics") || payload.message.includes("Agent")) traceClass = "agent-msg";
                traceLog(payload.message, traceClass);
            }
        }

        // Auto-refresh relevant tabs
        if (currentTab === "agents" && payload.message.includes("C2 link")) {
            loadAgentsGrid();
        }
        if (currentTab === "summary" && payload.message.includes("telemetry")) {
            fetchTopology();
        }
    };

    uiSocket.onclose = () => {
        logConsole("[SYSTEM] WebSocket stream disconnected. Reconnecting...", "warning");
        setTimeout(setupWebSocket, 5000);
    };

    uiSocket.onerror = () => {
        // Silent - onclose will handle reconnection
    };
}

function logConsole(message, type = "info") {
    const container = document.getElementById("console-stream");
    if (!container) return;

    const line = document.createElement("div");
    line.className = "console-line";

    switch (type) {
        case "success": line.classList.add("success-line"); break;
        case "warning": line.classList.add("warning-line"); break;
        case "error": line.classList.add("error-line"); break;
        case "agent_log": line.classList.add("agent-log"); break;
        default: line.classList.add("info-line"); break;
    }

    const time = new Date().toLocaleTimeString();
    line.innerText = `[${time}] ${message}`;

    container.appendChild(line);
    container.scrollTop = container.scrollHeight;

    // Keep console size manageable
    while (container.children.length > 200) {
        container.removeChild(container.firstChild);
    }
}

// ═══════════════════════════════════════════════════════════════════
// TAB 6: SETTINGS / PASSWORD MANAGEMENT
// ═══════════════════════════════════════════════════════════════════

function renderSettingsTab(viewport) {
    viewport.innerHTML = `
        <div class="downloads-layout" style="max-width: 600px;">
            <div class="card">
                <h3>${ICONS.settings} Change Admin Password</h3>
                <p class="card-subtitle">Securely update the administrator password in the database.</p>

                <div class="form-group mt-3">
                    <label>Current Password</label>
                    <input type="password" id="settings-current-password" placeholder="Enter current password">
                </div>
                <div class="form-group mt-3">
                    <label>New Password</label>
                    <input type="password" id="settings-new-password" placeholder="Enter new password">
                </div>
                <div class="form-group mt-3">
                    <label>Confirm New Password</label>
                    <input type="password" id="settings-confirm-password" placeholder="Confirm new password">
                </div>

                <div id="settings-error" class="login-error-msg mt-3" style="color: var(--danger); font-size: 0.8rem; margin-top: 8px;"></div>
                <div id="settings-success" class="login-success-msg mt-3" style="color: var(--success); font-size: 0.8rem; font-weight: 600; margin-top: 8px;"></div>

                <button class="btn btn-primary" id="btn-change-password" style="margin-top: 18px;">
                    ${ICONS.shield} Update Password
                </button>
            </div>
        </div>
    `;

    document.getElementById("btn-change-password").addEventListener("click", handlePasswordChange);
}

async function handlePasswordChange() {
    const currentPassword = document.getElementById("settings-current-password").value;
    const newPassword = document.getElementById("settings-new-password").value;
    const confirmPassword = document.getElementById("settings-confirm-password").value;
    const errDiv = document.getElementById("settings-error");
    const successDiv = document.getElementById("settings-success");
    const btn = document.getElementById("btn-change-password");

    errDiv.innerText = "";
    successDiv.innerText = "";

    if (!currentPassword || !newPassword || !confirmPassword) {
        errDiv.innerText = "All fields are required.";
        return;
    }

    if (newPassword !== confirmPassword) {
        errDiv.innerText = "New passwords do not match.";
        return;
    }

    btn.disabled = true;
    btn.innerHTML = `<span class="loading-spinner"></span> Updating...`;

    try {
        const res = await fetch("/api/auth/change-password", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: "admin",
                current_password: currentPassword,
                new_password: newPassword
            })
        });

        if (res.ok) {
            successDiv.innerText = "Password updated successfully! Redirecting in 2 seconds...";
            setTimeout(() => {
                // Logout to force login with new credentials
                localStorage.removeItem("admin_token");
                token = null;
                renderLoginPage();
            }, 2000);
        } else {
            const err = await res.json();
            errDiv.innerText = err.detail || "Failed to update password.";
            btn.disabled = false;
            btn.innerHTML = `${ICONS.shield} Update Password`;
        }
    } catch (e) {
        errDiv.innerText = "Error connecting to server.";
        btn.disabled = false;
        btn.innerHTML = `${ICONS.shield} Update Password`;
    }
}

// ═══════════════════════════════════════════════════════════════════
// AGENT EDIT MODAL
// ═══════════════════════════════════════════════════════════════════

function openEditAgentModal(id, name, ip, mac) {
    const modal = document.createElement("div");
    modal.className = "modal-overlay";
    modal.id = "edit-agent-modal";
    modal.innerHTML = `
        <div class="modal-card">
            <h3>Edit Agent Details</h3>
            <p style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 15px;">Modify source IP and MAC address for Agent: <strong>${name}</strong></p>
            
            <div class="form-group mt-3">
                <label>Source IP Address</label>
                <input type="text" id="edit-agent-ip" value="${ip}" placeholder="e.g. 10.0.10.15">
            </div>
            <div class="form-group mt-3">
                <label>Source MAC Address</label>
                <input type="text" class="mac-input" id="edit-agent-mac" value="${mac}" placeholder="e.g. 00:50:56:ab:cd:ef">
            </div>
            
            <div id="edit-agent-error" style="color: var(--danger); font-size: 0.8rem; margin-top: 8px;"></div>
            
            <div class="modal-actions">
                <button class="btn btn-secondary btn-sm" onclick="closeEditAgentModal()">Cancel</button>
                <button class="btn btn-primary btn-sm" id="btn-save-agent-edit">Save Changes</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    document.getElementById("btn-save-agent-edit").addEventListener("click", () => saveAgentEdit(id));
}

function closeEditAgentModal() {
    const modal = document.getElementById("edit-agent-modal");
    if (modal) {
        modal.remove();
    }
}

async function saveAgentEdit(id) {
    const ip = document.getElementById("edit-agent-ip").value;
    const mac = document.getElementById("edit-agent-mac").value;
    const errDiv = document.getElementById("edit-agent-error");
    const btn = document.getElementById("btn-save-agent-edit");
    
    btn.disabled = true;
    btn.innerHTML = `<span class="loading-spinner"></span> Saving...`;
    
    try {
        const res = await fetch(`/api/agents/${id}/edit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ip_address: ip, mac_address: mac })
        });
        
        if (res.ok) {
            closeEditAgentModal();
            loadAgentsGrid();
            fetchTopology(); // Refresh network topology to show new IP/MAC
        } else {
            const err = await res.json();
            errDiv.innerText = err.detail || "Failed to update agent.";
            btn.disabled = false;
            btn.innerHTML = `Save Changes`;
        }
    } catch (e) {
        errDiv.innerText = "Error connecting to server.";
        btn.disabled = false;
        btn.innerHTML = `Save Changes`;
    }
}


