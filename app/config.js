// TV Home User Configuration - Tailored for JVC LT-32KB116
window.CONFIG = {
  // Pinned apps displayed in the main favorites dock (User Priority)
  dockApps: [
    'pe.co.movistargo.itv',          // Movistar TV
    'com.viettel.media.tv360.bitel', // TV360 Bitel
    'youtube.leanback.v4',           // YouTube
    'amazon',                        // Prime Video
    'com.wbd.stream',                // HBO Max
    'com.pplus.webapp.prod-intl',    // Paramount+
    'netflix',                       // Netflix
    'com.disney.disneyplus-prod'     // Disney+
  ],

  // System or unwanted apps to hide from launcher grids
  hiddenApps: [
    'com.gathin.tvhome',
    'com.webos.app.home',
    'com.webos.app.discovery',
    'com.webos.app.notificationcenter',
    'com.webos.app.photovideo',
    'com.webos.app.softwareupdate',
    'com.webos.app.voice',
    'com.palmdts.devmode',
    // Bloatware & unused services hidden per user request:
    'amazon.alexa.view',             // Amazon Alexa
    'com.joinhighbrow.highbrow',     // Highbrow
    'com.webos.app.homeconnect',     // Panel del hogar
    'de.2kit.castbrowserlg',         // TV Cast
    'lgchannels.home'                // LG Channels
  ],

  // Default Live TV application ID
  liveTvApp: 'pe.co.movistargo.itv',

  // Grid layout column count
  columns: 6,

  // UI preferences
  clockFormat24h: false,
  showGreeting: true,
  ambientGlow: true
};
