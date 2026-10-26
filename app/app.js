/**
 * CleanYourTV - TV Home Launcher Runtime
 * Optimized for LG webOS Hub on JVC Smart TVs
 */

(function () {
  'use strict';

  // --- State & Variables ---
  var activeModal = null; // null | 'inputs' | 'settings'
  var currentSection = 'dock'; // 'header' | 'dock' | 'grid'
  var focusIndex = 0; // Index within active section or modal
  var activeAmbientLayer = 'A'; // 'A' or 'B' for crossfade

  var dockItems = [];
  var gridItems = [];
  var inputItems = [];
  var headerItems = [];

  var bridges = [];

  // --- Luna Service Bridge (webOS API) ---
  function luna(uri, params, cb) {
    if (typeof PalmServiceBridge === 'undefined') {
      console.log('[Luna Mock]', uri, params);
      if (cb) cb({ returnValue: true, mock: true });
      return;
    }

    try {
      var bridge = new PalmServiceBridge();
      bridge.onservicecallback = function (msg) {
        try {
          var parsed = JSON.parse(msg);
          if (cb) cb(parsed);
        } catch (e) {
          console.error('[Luna Callback Parse Error]', e, msg);
        }
        if (!params || !params.subscribe) {
          var idx = bridges.indexOf(bridge);
          if (idx !== -1) bridges.splice(idx, 1);
        }
      };
      bridge.call(uri, JSON.stringify(params || {}));
      bridges.push(bridge);
    } catch (err) {
      console.error('[Luna Call Failed]', uri, err);
    }
  }

  function launchApp(appId, params) {
    console.log('Launching application:', appId, params);
    luna('luna://com.webos.applicationManager/launch', {
      id: appId,
      params: params || {}
    });
  }

  // --- Clock & Greeting ---
  function updateClock() {
    var now = new Date();
    var hours = now.getHours();
    var minutes = now.getMinutes();
    var ampm = hours >= 12 ? 'PM' : 'AM';

    var greetingElem = document.getElementById('greeting');
    if (greetingElem) {
      var greeting = 'Bienvenido';
      if (hours < 12) greeting = 'Buenos días';
      else if (hours < 19) greeting = 'Buenas tardes';
      else greeting = 'Buenas noches';
      greetingElem.textContent = greeting;
    }

    var clockElem = document.getElementById('clock');
    if (clockElem) {
      var displayHours = hours;
      if (!window.CONFIG || !window.CONFIG.clockFormat24h) {
        displayHours = hours % 12 || 12;
      }
      var displayMinutes = minutes < 10 ? '0' + minutes : minutes;
      clockElem.textContent = (window.CONFIG && window.CONFIG.clockFormat24h)
        ? displayHours + ':' + displayMinutes
        : displayHours + ':' + displayMinutes + ' ' + ampm;
    }
  }

  // --- Ambient Glow Engine ---
  function updateAmbientGlow(colorHex) {
    if (!colorHex || (window.CONFIG && window.CONFIG.ambientGlow === false)) {
      colorHex = '#3b82f6';
    }

    var nextLayer = activeAmbientLayer === 'A' ? 'B' : 'A';
    var activeElem = document.getElementById('ambient' + activeAmbientLayer);
    var nextElem = document.getElementById('ambient' + nextLayer);

    if (!activeElem || !nextElem) return;

    // Convert hex to rgb for rgba gradient
    var r = 59, g = 130, b = 246;
    if (colorHex.charAt(0) === '#') {
      var hex = colorHex.substring(1);
      if (hex.length === 3) {
        r = parseInt(hex.charAt(0) + hex.charAt(0), 16);
        g = parseInt(hex.charAt(1) + hex.charAt(1), 16);
        b = parseInt(hex.charAt(2) + hex.charAt(2), 16);
      } else if (hex.length === 6) {
        r = parseInt(hex.substring(0, 2), 16);
        g = parseInt(hex.substring(2, 4), 16);
        b = parseInt(hex.substring(4, 6), 16);
      }
    }

    nextElem.style.background = 'radial-gradient(circle, rgba(' + r + ',' + g + ',' + b + ', 0.32) 0%, rgba(0, 0, 0, 0) 70%)';
    nextElem.style.opacity = '1';
    activeElem.style.opacity = '0';

    activeAmbientLayer = nextLayer;
  }

  // --- Initialization & UI Building ---
  function initData() {
    var config = window.CONFIG || {
      dockApps: [],
      hiddenApps: [],
      columns: 4
    };
    var data = window.TV_APPS || { apps: [], inputs: [] };
    var apps = data.apps || [];
    var inputs = data.inputs || [];

    var hiddenSet = {};
    (config.hiddenApps || []).forEach(function (id) {
      hiddenSet[id] = true;
    });

    // Filter visible apps
    var visibleApps = apps.filter(function (app) {
      return !hiddenSet[app.id] && !app.hidden;
    });

    // Populate dock
    var dockContainer = document.getElementById('dockContainer');
    dockContainer.innerHTML = '';
    dockItems = [];

    var dockAppIds = config.dockApps || [];
    var dockAppMap = {};

    dockAppIds.forEach(function (id) {
      var match = visibleApps.filter(function (a) { return a.id === id; })[0];
      if (match) {
        dockAppMap[id] = true;
        var btn = document.createElement('div');
        btn.className = 'dock-item';
        btn.dataset.id = match.id;
        btn.dataset.color = match.iconColor || match.bgColor || '#3b82f6';

        var img = document.createElement('img');
        img.src = match.largeIcon || match.icon || 'icon.png';
        img.alt = match.title;
        img.onerror = function () { this.src = 'icon.png'; };

        var title = document.createElement('div');
        title.className = 'title';
        title.textContent = match.title;

        btn.appendChild(img);
        btn.appendChild(title);
        dockContainer.appendChild(btn);
        dockItems.push({ elem: btn, data: match });
      }
    });

    // If dock is empty, populate with first few visible apps
    if (dockItems.length === 0 && visibleApps.length > 0) {
      visibleApps.slice(0, 5).forEach(function (match) {
        dockAppMap[match.id] = true;
        var btn = document.createElement('div');
        btn.className = 'dock-item';
        btn.dataset.id = match.id;
        btn.dataset.color = match.iconColor || match.bgColor || '#3b82f6';

        var img = document.createElement('img');
        img.src = match.largeIcon || match.icon || 'icon.png';
        img.onerror = function () { this.src = 'icon.png'; };

        var title = document.createElement('div');
        title.className = 'title';
        title.textContent = match.title;

        btn.appendChild(img);
        btn.appendChild(title);
        dockContainer.appendChild(btn);
        dockItems.push({ elem: btn, data: match });
      });
    }

    // Populate grid with all visible apps (including non-dock)
    var appsGrid = document.getElementById('appsGrid');
    appsGrid.innerHTML = '';
    gridItems = [];

    visibleApps.forEach(function (app) {
      var item = document.createElement('div');
      item.className = 'grid-item';
      item.dataset.id = app.id;
      item.dataset.color = app.iconColor || app.bgColor || '#3b82f6';

      var img = document.createElement('img');
      img.src = app.largeIcon || app.icon || 'icon.png';
      img.onerror = function () { this.src = 'icon.png'; };

      var title = document.createElement('div');
      title.className = 'title';
      title.textContent = app.title;

      item.appendChild(img);
      item.appendChild(title);
      appsGrid.appendChild(item);
      gridItems.push({ elem: item, data: app });
    });

    // Populate inputs
    var inputsList = document.getElementById('inputsList');
    inputsList.innerHTML = '';
    inputItems = [];

    inputs.forEach(function (inp) {
      var btn = document.createElement('div');
      btn.className = 'input-item';
      btn.dataset.id = inp.appId || inp.id;

      var label = document.createElement('div');
      label.className = 'title';
      label.textContent = inp.label || inp.id;

      var badge = document.createElement('div');
      badge.className = 'input-badge' + (inp.connected ? ' active' : '');
      badge.textContent = inp.connected ? 'Active Signal' : 'No Signal';

      btn.appendChild(label);
      btn.appendChild(badge);
      inputsList.appendChild(btn);
      inputItems.push({ elem: btn, data: inp });
    });

    // Header buttons
    headerItems = [
      { elem: document.getElementById('btnInputs'), action: 'inputs' },
      { elem: document.getElementById('btnSettings'), action: 'settings' }
    ];

    // Default focus
    currentSection = 'dock';
    focusIndex = 0;
    applyFocus();
  }

  // --- Focus Engine ---
  function clearAllFocus() {
    var focusedElems = document.querySelectorAll('.focused');
    for (var i = 0; i < focusedElems.length; i++) {
      focusedElems[i].classList.remove('focused');
    }
  }

  function getAppCategory(appId, title) {
    var id = (appId || '').toLowerCase();
    if (id.indexOf('movistar') !== -1) return 'TV en Vivo, Deportes y Canales';
    if (id.indexOf('youtube') !== -1) return 'Videos, Música y Creadores';
    if (id.indexOf('amazon') !== -1 || id.indexOf('prime') !== -1) return 'Películas, Series y Contenido Exclusivo';
    if (id.indexOf('wbd') !== -1 || id.indexOf('max') !== -1) return 'Cine, HBO Originals y Warner Bros';
    if (id.indexOf('pplus') !== -1 || id.indexOf('paramount') !== -1) return 'Series Premium, Cine y SHOWTIME';
    if (id.indexOf('netflix') !== -1) return 'Películas, Series y Documentales';
    if (id.indexOf('disney') !== -1) return 'Disney, Pixar, Marvel y Star Wars';
    if (id.indexOf('star') !== -1) return 'Deportes ESPN y Series';
    if (id.indexOf('browser') !== -1) return 'Navegación Web en Pantalla Completa';
    if (id.indexOf('bitel') !== -1 || id.indexOf('360') !== -1) return 'Canales en Vivo y Noticias';
    if (id.indexOf('america') !== -1) return 'Televisión Peruana en Vivo';
    if (id.indexOf('music') !== -1) return 'Música y Reproducción de Audio';
    return 'Aplicación de Streaming';
  }

  function updateTopShelf(title, appId, colorHex) {
    var titleElem = document.getElementById('shelfTitle');
    var tagElem = document.getElementById('shelfTag');
    if (titleElem) {
      titleElem.textContent = title || 'TV Home';
    }
    if (tagElem) {
      tagElem.textContent = getAppCategory(appId, title);
    }
    if (colorHex) {
      document.documentElement.style.setProperty('--glow-color', colorHex + '99');
    }
  }

  function applyFocus() {
    clearAllFocus();

    if (activeModal === 'inputs') {
      if (inputItems.length > 0) {
        if (focusIndex < 0) focusIndex = 0;
        if (focusIndex >= inputItems.length) focusIndex = inputItems.length - 1;
        inputItems[focusIndex].elem.classList.add('focused');
      }
      return;
    }

    if (activeModal === 'settings') {
      return;
    }

    if (currentSection === 'header') {
      if (focusIndex < 0) focusIndex = 0;
      if (focusIndex >= headerItems.length) focusIndex = headerItems.length - 1;
      headerItems[focusIndex].elem.classList.add('focused');
      updateAmbientGlow('#3b82f6');
      updateTopShelf('Ajustes del Sistema', 'system', '#3b82f6');
    } else if (currentSection === 'dock') {
      if (dockItems.length > 0) {
        if (focusIndex < 0) focusIndex = 0;
        if (focusIndex >= dockItems.length) focusIndex = dockItems.length - 1;
        var current = dockItems[focusIndex];
        current.elem.classList.add('focused');
        var color = current.data.iconColor || current.data.bgColor || '#3b82f6';
        updateAmbientGlow(color);
        updateTopShelf(current.data.title, current.data.id, color);
      }
    } else if (currentSection === 'grid') {
      if (gridItems.length > 0) {
        if (focusIndex < 0) focusIndex = 0;
        if (focusIndex >= gridItems.length) focusIndex = gridItems.length - 1;
        var currentGrid = gridItems[focusIndex];
        currentGrid.elem.classList.add('focused');
        currentGrid.elem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        var gColor = currentGrid.data.iconColor || currentGrid.data.bgColor || '#3b82f6';
        updateAmbientGlow(gColor);
        updateTopShelf(currentGrid.data.title, currentGrid.data.id, gColor);
      }
    }
  }

  function openModal(name) {
    activeModal = name;
    var overlay = document.getElementById(name + 'Modal');
    if (overlay) overlay.classList.add('active');
    focusIndex = 0;
    applyFocus();
  }

  function closeModal() {
    if (!activeModal) return;
    var overlay = document.getElementById(activeModal + 'Modal');
    if (overlay) overlay.classList.remove('active');
    activeModal = null;
    applyFocus();
  }

  // --- Key Navigation Handler ---
  function handleKeyDown(e) {
    var keyCode = e.keyCode || e.which;
    console.log('[Key Event] code:', keyCode);

    // Modal navigation
    if (activeModal) {
      if (keyCode === 461 || keyCode === 8 || keyCode === 27) {
        // Back / Return / Esc
        e.preventDefault();
        closeModal();
        return;
      }

      if (activeModal === 'inputs' && inputItems.length > 0) {
        if (keyCode === 37) { // Left
          if (focusIndex % 2 === 1) focusIndex--;
        } else if (keyCode === 39) { // Right
          if (focusIndex % 2 === 0 && focusIndex + 1 < inputItems.length) focusIndex++;
        } else if (keyCode === 38) { // Up
          if (focusIndex >= 2) focusIndex -= 2;
        } else if (keyCode === 40) { // Down
          if (focusIndex + 2 < inputItems.length) focusIndex += 2;
        } else if (keyCode === 13) { // OK
          var targetInput = inputItems[focusIndex].data;
          closeModal();
          if (targetInput.appId) {
            launchApp(targetInput.appId);
          }
        }
        applyFocus();
      }
      return;
    }

    // Main Launcher Navigation
    var cols = (window.CONFIG && window.CONFIG.columns) || 4;

    switch (keyCode) {
      case 37: // Left
        e.preventDefault();
        if (currentSection === 'header') {
          if (focusIndex > 0) focusIndex--;
        } else if (currentSection === 'dock') {
          if (focusIndex > 0) focusIndex--;
        } else if (currentSection === 'grid') {
          if (focusIndex > 0) focusIndex--;
        }
        break;

      case 39: // Right
        e.preventDefault();
        if (currentSection === 'header') {
          if (focusIndex < headerItems.length - 1) focusIndex++;
        } else if (currentSection === 'dock') {
          if (focusIndex < dockItems.length - 1) focusIndex++;
        } else if (currentSection === 'grid') {
          if (focusIndex < gridItems.length - 1) focusIndex++;
        }
        break;

      case 38: // Up
        e.preventDefault();
        if (currentSection === 'grid') {
          if (focusIndex >= cols) {
            focusIndex -= cols;
          } else {
            currentSection = 'dock';
            focusIndex = Math.min(focusIndex, dockItems.length - 1);
          }
        } else if (currentSection === 'dock') {
          currentSection = 'header';
          focusIndex = 0;
        }
        break;

      case 40: // Down
        e.preventDefault();
        if (currentSection === 'header') {
          currentSection = 'dock';
          focusIndex = 0;
        } else if (currentSection === 'dock') {
          if (gridItems.length > 0) {
            currentSection = 'grid';
            focusIndex = 0;
          }
        } else if (currentSection === 'grid') {
          if (focusIndex + cols < gridItems.length) {
            focusIndex += cols;
          }
        }
        break;

      case 13: // OK / Enter
        e.preventDefault();
        if (currentSection === 'header') {
          var action = headerItems[focusIndex].action;
          openModal(action);
        } else if (currentSection === 'dock') {
          if (dockItems[focusIndex]) {
            launchApp(dockItems[focusIndex].data.id);
          }
        } else if (currentSection === 'grid') {
          if (gridItems[focusIndex]) {
            launchApp(gridItems[focusIndex].data.id);
          }
        }
        break;

      case 461: // Back (webOS Remote)
      case 8:   // Backspace
      case 27:  // Escape
        e.preventDefault();
        if (currentSection === 'grid') {
          currentSection = 'dock';
          focusIndex = 0;
          applyFocus();
        } else if (currentSection === 'header') {
          currentSection = 'dock';
          focusIndex = 0;
          applyFocus();
        }
        break;

      // Numeric Key Shortcuts (1-9)
      case 49: // '1'
      case 50: // '2'
      case 51: // '3'
      case 52: // '4'
      case 53: // '5'
      case 54: // '6'
      case 55: // '7'
      case 56: // '8'
      case 57: // '9'
        var numIdx = keyCode - 49;
        if (dockItems[numIdx]) {
          launchApp(dockItems[numIdx].data.id);
        }
        break;

      // Color Keys
      case 403: // Red: Inputs
        openModal('inputs');
        break;
      case 404: // Green: Live TV
        var liveId = (window.CONFIG && window.CONFIG.liveTvApp) || 'com.webos.app.livetv';
        launchApp(liveId);
        break;
      case 406: // Blue: Settings
        openModal('settings');
        break;
    }

    applyFocus();
  }

  // --- Initialize on DOMContentLoaded ---
  window.addEventListener('DOMContentLoaded', function () {
    updateClock();
    setInterval(updateClock, 1000);

    initData();
    window.addEventListener('keydown', handleKeyDown);

    // Subscribe to network status
    luna('luna://com.palm.connectionmanager/getStatus', { subscribe: true }, function (res) {
      var elem = document.getElementById('networkStatus');
      if (elem && res) {
        if (res.isInternetConnectionAvailable) {
          elem.textContent = res.wifi && res.wifi.ssid ? res.wifi.ssid : 'Connected';
        } else {
          elem.textContent = 'Offline';
        }
      }
    });

    console.log('TV Home launcher initialized successfully.');
  });
})();
