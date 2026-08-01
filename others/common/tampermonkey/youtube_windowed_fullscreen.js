// ==UserScript==
// @name         YouTube Windowed Fullscreen Hotkey
// @namespace    https://github.com/openai/codex
// @version      1.2.0
// @description  Toggle YouTube windowed fullscreen with the ₩ / ` key.
// @match        https://www.youtube.com/*
// @match        https://youtube.com/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function () {
  "use strict";

  const ACTIVE_CLASS = "yt-windowed-fullscreen-hotkey-active";
  const TRIGGER_KEYS = new Set(["`", "₩", "\\"]);
  const TRIGGER_CODES = new Set(["Backquote"]);
  const RESIZE_DELAYS_MS = [0, 60, 180, 420];

  let savedScrollY = 0;

  const css = `
    html.${ACTIVE_CLASS},
    html.${ACTIVE_CLASS} body {
      width: 100% !important;
      height: 100% !important;
      overflow: hidden !important;
      background: #000 !important;
    }

    html.${ACTIVE_CLASS} body {
      margin: 0 !important;
    }

    html.${ACTIVE_CLASS} ytd-app,
    html.${ACTIVE_CLASS} #content,
    html.${ACTIVE_CLASS} #page-manager,
    html.${ACTIVE_CLASS} ytd-watch-flexy {
      overflow: visible !important;
    }

    html.${ACTIVE_CLASS} ytd-masthead,
    html.${ACTIVE_CLASS} #masthead-container,
    html.${ACTIVE_CLASS} ytd-mini-guide-renderer,
    html.${ACTIVE_CLASS} #guide,
    html.${ACTIVE_CLASS} ytd-miniplayer,
    html.${ACTIVE_CLASS} ytd-live-chat-frame,
    html.${ACTIVE_CLASS} #chat,
    html.${ACTIVE_CLASS} #chat-container,
    html.${ACTIVE_CLASS} #chatframe,
    html.${ACTIVE_CLASS} #secondary,
    html.${ACTIVE_CLASS} #secondary-inner,
    html.${ACTIVE_CLASS} #below,
    html.${ACTIVE_CLASS} #comments,
    html.${ACTIVE_CLASS} #panels,
    html.${ACTIVE_CLASS} #playlist,
    html.${ACTIVE_CLASS} ytd-merch-shelf-renderer,
    html.${ACTIVE_CLASS} ytd-reel-shelf-renderer {
      display: none !important;
    }

    html.${ACTIVE_CLASS} ytd-watch-flexy #columns,
    html.${ACTIVE_CLASS} ytd-watch-flexy #primary,
    html.${ACTIVE_CLASS} ytd-watch-flexy #primary-inner {
      display: block !important;
      width: 100vw !important;
      height: 100vh !important;
      min-width: 0 !important;
      min-height: 0 !important;
      max-width: none !important;
      max-height: none !important;
      margin: 0 !important;
      padding: 0 !important;
    }

    html.${ACTIVE_CLASS} ytd-watch-flexy #primary-inner > :not(#player) {
      display: none !important;
    }

    html.${ACTIVE_CLASS} ytd-watch-flexy[theater],
    html.${ACTIVE_CLASS} ytd-watch-flexy[fullscreen],
    html.${ACTIVE_CLASS} ytd-watch-flexy {
      --ytd-watch-flexy-chat-max-height: 0 !important;
      --ytd-watch-flexy-chat-width: 0 !important;
      --ytd-watch-flexy-max-player-width: 100vw !important;
      --ytd-watch-flexy-min-player-height: 100vh !important;
      --ytd-watch-flexy-panel-max-height: 0 !important;
      --ytd-watch-flexy-width-ratio: 16 !important;
      --ytd-watch-flexy-height-ratio: 9 !important;
    }

    html.${ACTIVE_CLASS} ytd-player,
    html.${ACTIVE_CLASS} #player,
    html.${ACTIVE_CLASS} #player-container,
    html.${ACTIVE_CLASS} #player-container-inner,
    html.${ACTIVE_CLASS} #player-container-outer,
    html.${ACTIVE_CLASS} #player-theater-container,
    html.${ACTIVE_CLASS} #movie_player,
    html.${ACTIVE_CLASS} .html5-video-player {
      position: fixed !important;
      inset: 0 !important;
      width: 100vw !important;
      height: 100vh !important;
      min-width: 0 !important;
      min-height: 0 !important;
      max-width: none !important;
      max-height: none !important;
      margin: 0 !important;
      padding: 0 !important;
      transform: none !important;
      z-index: 2147483647 !important;
      background: #000 !important;
    }

    html.${ACTIVE_CLASS} .html5-video-container {
      position: absolute !important;
      inset: 0 !important;
      width: 100% !important;
      height: 100% !important;
      overflow: hidden !important;
    }

    html.${ACTIVE_CLASS} .html5-main-video {
      position: absolute !important;
      width: 100% !important;
      height: 100% !important;
      top: 0 !important;
      left: 0 !important;
      transform: none !important;
      object-fit: contain !important;
    }

    html.${ACTIVE_CLASS} .ytp-chrome-bottom {
      left: 12px !important;
      right: 12px !important;
      width: calc(100vw - 24px) !important;
    }

    html.${ACTIVE_CLASS} .ytp-chrome-top,
    html.${ACTIVE_CLASS} .ytp-gradient-top,
    html.${ACTIVE_CLASS} .ytp-gradient-bottom,
    html.${ACTIVE_CLASS} .ytp-popup {
      width: 100% !important;
    }
  `;

  function installStyle() {
    const style = document.createElement("style");
    style.id = "yt-windowed-fullscreen-hotkey-style";
    style.textContent = css;
    (document.head || document.documentElement).appendChild(style);
  }

  function isActive() {
    return document.documentElement.classList.contains(ACTIVE_CLASS);
  }

  function getPlayer() {
    return document.querySelector("#movie_player.html5-video-player, .html5-video-player");
  }

  function isTypingTarget(target) {
    if (!(target instanceof Element)) return false;

    const tagName = target.tagName.toLowerCase();
    return (
      target.isContentEditable ||
      tagName === "input" ||
      tagName === "textarea" ||
      tagName === "select" ||
      Boolean(target.closest("[contenteditable='true'], ytd-searchbox, yt-searchbox"))
    );
  }

  function syncPlayerSize() {
    const player = getPlayer();
    if (!player) return;

    window.dispatchEvent(new Event("resize"));
    player.dispatchEvent(new Event("resize"));

    if (typeof player.setSize === "function") {
      try {
        player.setSize(window.innerWidth, window.innerHeight);
      } catch (_) {
        // YouTube changes this API occasionally; CSS still handles the layout.
      }
    }
  }

  function syncPlayerSizeSoon() {
    for (const delay of RESIZE_DELAYS_MS) {
      window.setTimeout(syncPlayerSize, delay);
    }
  }

  function setActive(nextActive) {
    if (nextActive && !getPlayer()) return;

    if (nextActive) {
      savedScrollY = window.scrollY;
    }

    document.documentElement.classList.toggle(ACTIVE_CLASS, nextActive);
    document.body?.classList.toggle(ACTIVE_CLASS, nextActive);

    if (!nextActive) {
      window.scrollTo(0, savedScrollY);
    }

    syncPlayerSizeSoon();
  }

  function toggleActive() {
    setActive(!isActive());
  }

  function isTriggerKey(event) {
    return TRIGGER_KEYS.has(event.key) || TRIGGER_CODES.has(event.code);
  }

  function onKeyDown(event) {
    if (event.repeat || event.altKey || event.ctrlKey || event.metaKey) return;

    if (event.key === "Escape" && isActive()) {
      event.preventDefault();
      event.stopPropagation();
      setActive(false);
      return;
    }

    if (!isTriggerKey(event) || isTypingTarget(event.target)) return;

    event.preventDefault();
    event.stopPropagation();
    toggleActive();
  }

  function cleanupIfPlayerGone() {
    window.setTimeout(() => {
      if (isActive() && !getPlayer()) {
        setActive(false);
      }
    }, 500);
  }

  installStyle();
  document.addEventListener("keydown", onKeyDown, true);
  window.addEventListener("resize", () => {
    if (isActive()) syncPlayerSizeSoon();
  });
  document.addEventListener("yt-navigate-finish", cleanupIfPlayerGone);
})();
