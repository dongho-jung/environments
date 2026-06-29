// ==UserScript==
// @name         Naver Dict - Backquote Add Word
// @namespace    local
// @version      0.5
// @description  ja.dict.naver.com에서 ` 키를 누르면 첫 번째 단어장 추가 버튼을 클릭하고, 필요하면 저장 버튼까지 클릭
// @match        https://ja.dict.naver.com/*
// @grant        none
// @run-at       document-start
// ==/UserScript==

(() => {
  'use strict';

  const debug = true;

  const openSelectors = [
    '#btnAddWordBook',
    'button.unit_add_wordbook._btn_add_wordbook:not(._btn_add_wordbook_example)',
    'button[class*="add_wordbook"]:not(._btn_add_wordbook_example)',
    'button[class*="wordbook"]:not(._btn_add_wordbook_example)',
  ];

  const layerSelectors = [
    '#pcLyAddWordBook',
    '[id*="AddWordBook"]',
    '[class*="AddWordBook"]',
    '[role="dialog"]',
  ];

  const saveSelectors = [
    '#pcLyAddWordBook a._basic_save',
    '#pcLyAddWordBook button._basic_save',
    '#pcLyAddWordBook a._btn_common_default_add',
    '#pcLyAddWordBook button._btn_common_default_add',
    '#pcLyAddWordBook .button_area a',
    '#pcLyAddWordBook .button_area button',
  ];

  let busy = false;
  let lastTriggeredAt = 0;
  let suppressBeforeInputUntil = 0;

  function log(...args) {
    if (debug) console.log('[naver-wordbook]', ...args);
  }

  function isVisible(el) {
    if (!el) return false;

    const style = window.getComputedStyle(el);
    if (style.display === 'none') return false;
    if (style.visibility === 'hidden') return false;
    if (Number(style.opacity) === 0) return false;

    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function isDisabled(el) {
    return (
      el.disabled ||
      el.getAttribute('aria-disabled') === 'true' ||
      el.classList.contains('disabled') ||
      el.classList.contains('is_disabled')
    );
  }

  function isBadOpenCandidate(el) {
    if (!el) return true;

    if (el.id === 'btnAddAllReviewedWords') return true;
    if (el.classList.contains('_btn_add_wordbook_example')) return true;

    const text = el.textContent.trim();

    if (/내 단어장|전체|전체추가|my wordbook/i.test(text)) return true;
    if (el.closest('#_id_more_layer')) return true;

    return false;
  }

  function findOpenButton() {
    for (const selector of openSelectors) {
      const els = [...document.querySelectorAll(selector)];

      for (const el of els) {
        if (!isVisible(el)) continue;
        if (isDisabled(el)) continue;
        if (isBadOpenCandidate(el)) continue;

        log('open button found by selector:', selector, el);
        return el;
      }
    }

    const fallbackCandidates = [...document.querySelectorAll('button, a, [role="button"]')]
      .filter((el) => isVisible(el) && !isDisabled(el))
      .filter((el) => !isBadOpenCandidate(el))
      .filter((el) => {
        const s = [
          el.id,
          el.className,
          el.getAttribute('aria-label'),
          el.getAttribute('title'),
          el.textContent,
        ].join(' ');

        return /add_wordbook|wordbook|단어장/i.test(s);
      });

    if (fallbackCandidates.length > 0) {
      log('open button fallback candidate:', fallbackCandidates[0], fallbackCandidates);
      return fallbackCandidates[0];
    }

    return null;
  }

  function findLayerRoots() {
    const roots = [];

    for (const selector of layerSelectors) {
      for (const el of document.querySelectorAll(selector)) {
        if (!isVisible(el)) continue;
        if (el.id === '_id_more_layer') continue;
        if (el.classList.contains('Nnav_item')) continue;

        roots.push(el);
      }
    }

    return [...new Set(roots)];
  }

  function findSaveButton() {
    for (const selector of saveSelectors) {
      const els = [...document.querySelectorAll(selector)];

      for (const el of els) {
        if (!isVisible(el)) continue;
        if (isDisabled(el)) continue;

        log('save button found by strict selector:', selector, el);
        return el;
      }
    }

    const roots = findLayerRoots();

    for (const root of roots) {
      const candidates = [...root.querySelectorAll('a, button, [role="button"]')]
        .filter((el) => isVisible(el) && !isDisabled(el))
        .filter((el) => {
          const text = el.textContent.trim();
          const aria = el.getAttribute('aria-label') || '';
          const title = el.getAttribute('title') || '';
          const className = String(el.className || '');

          const s = `${text} ${aria} ${title} ${className}`;

          if (/취소|닫기|cancel|close/i.test(s)) return false;

          return (
            /^저장$/.test(text) ||
            /^추가$/.test(text) ||
            /^확인$/.test(text) ||
            /_basic_save|_btn_common_default_add/i.test(className) ||
            /\bsave\b|\badd\b/i.test(s)
          );
        });

      if (candidates.length > 0) {
        log('save button layer candidate:', candidates[0], candidates);
        return candidates[0];
      }
    }

    return null;
  }

  function clickLikeUser(el) {
    if (!el) return false;

    try {
      el.scrollIntoView({ block: 'center', inline: 'center' });
    } catch {}

    try {
      el.focus?.({ preventScroll: true });
    } catch {}

    const mouseOptions = {
      bubbles: true,
      cancelable: true,
      view: window,
      button: 0,
      buttons: 1,
    };

    const pointerOptions = {
      ...mouseOptions,
      pointerId: 1,
      pointerType: 'mouse',
      isPrimary: true,
    };

    try {
      if (window.PointerEvent) {
        el.dispatchEvent(new PointerEvent('pointerdown', pointerOptions));
      }

      el.dispatchEvent(new MouseEvent('mousedown', mouseOptions));

      if (window.PointerEvent) {
        el.dispatchEvent(new PointerEvent('pointerup', pointerOptions));
      }

      el.dispatchEvent(new MouseEvent('mouseup', mouseOptions));
      el.dispatchEvent(new MouseEvent('click', mouseOptions));

      log('clicked:', el);
      return true;
    } catch (err) {
      log('click event failed, fallback to el.click():', err);
      el.click();
      return true;
    }
  }

  function waitFor(fn, timeout = 2500) {
    return new Promise((resolve) => {
      const existing = fn();

      if (existing) {
        resolve(existing);
        return;
      }

      const startedAt = Date.now();

      const timer = setInterval(() => {
        const found = fn();

        if (found) {
          cleanup();
          resolve(found);
          return;
        }

        if (Date.now() - startedAt >= timeout) {
          cleanup();
          resolve(fn());
        }
      }, 80);

      const observer = new MutationObserver(() => {
        const found = fn();

        if (found) {
          cleanup();
          resolve(found);
        }
      });

      function cleanup() {
        clearInterval(timer);
        observer.disconnect();
      }

      const root = document.documentElement || document;
      observer.observe(root, {
        childList: true,
        subtree: true,
        attributes: true,
      });
    });
  }

  function dumpCandidates() {
    const candidates = [...document.querySelectorAll('button, a, [role="button"]')]
      .filter((el) => isVisible(el))
      .slice(0, 100)
      .map((el) => ({
        tag: el.tagName,
        id: el.id,
        className: String(el.className),
        text: el.textContent.trim().slice(0, 80),
        ariaLabel: el.getAttribute('aria-label'),
        title: el.getAttribute('title'),
        html: el.outerHTML.slice(0, 300),
      }));

    log('clickable candidates:', candidates);
  }

  async function runFlow() {
    log('runFlow start');

    // 이미 단어장 레이어가 열려 있는 경우에만 저장 버튼을 먼저 클릭
    const alreadyOpenSaveBtn = findSaveButton();
    if (alreadyOpenSaveBtn) {
      log('save button already visible');
      clickLikeUser(alreadyOpenSaveBtn);
      return;
    }

    const openBtn = findOpenButton();

    if (!openBtn) {
      log('open button not found');
      dumpCandidates();
      return;
    }

    clickLikeUser(openBtn);

    // 새 네이버 구조에서는 여기서 이미 추가가 끝날 수도 있음.
    // 그래도 레이어가 뜨는 경우를 위해 저장 버튼을 한 번 더 기다림.
    const saveBtn = await waitFor(findSaveButton, 2500);

    if (saveBtn) {
      log('save button found after opening');
      clickLikeUser(saveBtn);
      return;
    }

    log('save button not found after opening; maybe first click already handled it');
  }

  async function trigger(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
    }

    const now = Date.now();

    if (busy || now - lastTriggeredAt < 250) {
      log('ignored: busy or too soon');
      return;
    }

    busy = true;
    lastTriggeredAt = now;
    suppressBeforeInputUntil = now + 500;

    try {
      await runFlow();
    } catch (err) {
      console.error('[naver-wordbook] failed:', err);
    } finally {
      setTimeout(() => {
        busy = false;
      }, 150);
    }
  }

  function onKeyDown(e) {
    const isBackquote = e.code === 'Backquote' || e.key === '`';

    if (!isBackquote) return;
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.repeat) return;

    log('keydown captured:', {
      key: e.key,
      code: e.code,
      target: e.target,
      url: location.href,
    });

    trigger(e);
  }

  function onBeforeInput(e) {
    if (e.data !== '`') return;

    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();

    if (Date.now() < suppressBeforeInputUntil) return;

    log('beforeinput captured:', {
      data: e.data,
      target: e.target,
      url: location.href,
    });

    trigger(e);
  }

  window.addEventListener('keydown', onKeyDown, {
    capture: true,
    passive: false,
  });

  document.addEventListener('keydown', onKeyDown, {
    capture: true,
    passive: false,
  });

  window.addEventListener('beforeinput', onBeforeInput, {
    capture: true,
    passive: false,
  });

  document.addEventListener('beforeinput', onBeforeInput, {
    capture: true,
    passive: false,
  });

  log('loaded:', location.href);
})();