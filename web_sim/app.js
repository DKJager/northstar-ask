// 3Dogs Nexus — authorship fingerprint alexa-plus-v2-973f2125
/* Northstar Ask — simulated Alexa+ front end.
 *
 * Talks to the local bridge (web_sim/bridge.py) via plain JSON POSTs.
 * Voice input uses the browser Web Speech API with a text fallback.
 * Spoken replies are read aloud with SpeechSynthesis and rendered as
 * Echo Show-style cards. No external libraries or CDNs.
 */
(function () {
  "use strict";

  var conversation = document.getElementById("conversation");
  var cardArea = document.getElementById("card-area");
  var textForm = document.getElementById("text-form");
  var textInput = document.getElementById("text-input");
  var micBtn = document.getElementById("mic-btn");
  var briefBtn = document.getElementById("brief-btn");
  var explainBtn = document.getElementById("explain-btn");
  var correctBtn = document.getElementById("correct-btn");
  var hint = document.getElementById("speech-support-hint");

  var sessionId = (window.crypto && typeof crypto.randomUUID === "function")
    ? crypto.randomUUID()
    : "web-" + Math.random().toString(16).slice(2, 14);
  var lastQuestion = "";

  // Check if we're in sample mode by making a test request
  const STATUS_PATH = "/api/status";

  function detectMode() {
    fetch(STATUS_PATH, {
      method: "GET",
      headers: { "Content-Type": "application/json" }
    }).then(function(resp) {
      return resp.json();
    }).then(function(data) {
      if (data.sample_mode) {
        hint.textContent = "Voice input uses your browser's Web Speech API when available; typing always works. Answers are precomputed from the fictional dataset.";
      } else {
        hint.textContent = "Voice input uses your browser's Web Speech API when available; typing always works. Answers come from a configured backend service.";
      }
    }).catch(function() {
      hint.textContent = "Voice input uses your browser's Web Speech API when available; typing always works. Answers come from a backend service.";
    });
  }

  function scrollToBottom() {
    conversation.scrollTop = conversation.scrollHeight;
  }

  function addBubble(text, who) {
    var div = document.createElement("div");
    div.className = "bubble " + who;
    var p = document.createElement("p");
    p.textContent = text;
    div.appendChild(p);
    conversation.appendChild(div);
    scrollToBottom();
    return div;
  }

  function speak(text) {
    if (!("speechSynthesis" in window)) { return; }
    try {
      window.speechSynthesis.cancel();
      var utter = new SpeechSynthesisUtterance(text);
      utter.rate = 1.0;
      window.speechSynthesis.speak(utter);
    } catch (err) { /* spoken output is a bonus; text always shows */ }
  }

  // Builds a card element. It does NOT attach it to the page: every
  // response (ask, explain, brief) goes through renderCards() below so a
  // single card and a brief's card list render through the same path.
  function renderCard(card) {
    if (!card) { return; }
    // Validate confidence for CSS class safety
    var validConfidences = { "low": "low", "medium": "medium", "high": "high" };
    var confidenceClass = validConfidences[card.confidence] || "medium";
    var el = document.createElement("div");
    el.className = "card confidence-" + confidenceClass;

    var title = document.createElement("h3");
    title.textContent = card.title || "Result";
    el.appendChild(title);

    if (card.columns && card.rows && card.rows.length) {
      var table = document.createElement("table");
      var thead = document.createElement("thead");
      var headRow = document.createElement("tr");
      card.columns.forEach(function (col) {
        var th = document.createElement("th");
        th.textContent = col;
        headRow.appendChild(th);
      });
      thead.appendChild(headRow);
      table.appendChild(thead);
      var tbody = document.createElement("tbody");
      card.rows.slice(0, 10).forEach(function (row) {
        var tr = document.createElement("tr");
        row.forEach(function (cell) {
          var td = document.createElement("td");
          td.textContent = cell;
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      el.appendChild(table);
    }

    if (card.chart_hint === "bar" && card.rows && card.rows.length) {
      var bars = document.createElement("div");
      bars.className = "bar-chart";
      card.rows.slice(0, 5).forEach(function (row, i) {
        var bar = document.createElement("div");
        bar.className = "bar bar-" + i;
        bar.style.width = (90 - i * 15) + "%";
        bar.textContent = String(row[0]);
        bars.appendChild(bar);
      });
      el.appendChild(bars);
    }

    var meta = document.createElement("p");
    meta.className = "card-meta";
    var bits = [];
    if (card.confidence) { bits.push("Confidence: " + card.confidence); }
    if (card.sources && card.sources.length) {
      bits.push("Sources: " + card.sources.join(", "));
    }
    meta.textContent = bits.join(" · ");
    el.appendChild(meta);

    return el;
  }

  function renderCards(cards) {
    // Clear existing cards
    while (cardArea.firstChild) {
      cardArea.removeChild(cardArea.firstChild);
    }
    
    // Render each card
    (cards || []).forEach(function(card) {
      if (!card) { return; }
      var cardElement = renderCard(card);
      if (cardElement) {
        cardArea.appendChild(cardElement);
      }
    });
  }

  // Single-card responses (/api/ask, /api/explain) carry `card`; the brief
  // carries `cards`. Normalise both onto the renderCards() path.
  function cardsFromBody(body) {
    if (body && body.cards && body.cards.length) { return body.cards; }
    if (body && body.card) { return [body.card]; }
    return [];
  }

  function postJson(path, payload, onOk, onErr) {
    payload.session_id = sessionId;
    
    // Add timeout functionality
    var controller = new AbortController();
    var timeoutId = setTimeout(function() {
      controller.abort();
    }, 10000); // 10 second timeout
    
    fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal
    }).then(function (resp) {
      clearTimeout(timeoutId); // Clear timeout on response
      return resp.text().then(function (text) {
        var body = {};
        try {
          body = JSON.parse(text);
        } catch (e) {
          // Not JSON — pass through the raw text for error reporting
          body = { error: "Server returned non-JSON response (status " + resp.status + "): " + text.substring(0, 200) };
        }
        return { status: resp.status, body: body };
      });
    }).then(function (result) {
      if (result.status >= 200 && result.status < 300) {
        onOk(result.body);
      } else {
        onErr(result.body.error || "The service returned an error.");
      }
    }).catch(function (error) {
      clearTimeout(timeoutId); // Clear timeout on error
      if (error.name === 'AbortError') {
        // Timeout: the caller's error path removes the "Thinking…" bubble.
        onErr("Request timed out. Please try again.");
      } else {
        onErr("Could not reach the local bridge. Is web_sim/bridge.py running?");
      }
    });
    
    // Return the pending bubble so the caller can remove it on reply or error
    return addBubble("Thinking…", "assistant pending");
  }

  function ask(question) {
    if (!question) { return; }
    lastQuestion = question;
    addBubble(question, "user");
    var pending = postJson("/api/ask", { question: question }, function (body) {
      pending.remove();
      addBubble(body.spoken || "(no spoken reply)", "assistant");
      speak(body.spoken || "");
      // Same path as the brief, so the Echo Show card actually appears.
      renderCards(cardsFromBody(body));
    }, function (message) {
      pending.remove();
      addBubble("Sorry — " + message, "assistant error");
    });
  }

  textForm.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var q = textInput.value.trim();
    textInput.value = "";
    ask(q);
  });

  briefBtn.addEventListener("click", function () {
    lastQuestion = "Weekly business brief";
    addBubble("Give me the weekly business brief.", "user");
    var pending = postJson("/api/brief", {}, function (body) {
      pending.remove();
      addBubble(body.spoken || "(no spoken reply)", "assistant");
      speak(body.spoken || "");
      renderCards(cardsFromBody(body));
    }, function (message) {
      pending.remove();
      addBubble("Sorry — " + message, "assistant error");
    });
  });

  explainBtn.addEventListener("click", function () {
    lastQuestion = "Explain last answer";
    addBubble("Explain that in business terms.", "user");
    var pending = postJson("/api/explain", {}, function (body) {
      pending.remove();
      addBubble(body.spoken || "(nothing to explain yet)", "assistant");
      speak(body.spoken || "");
      // An explanation with a card replaces the display; without one the
      // previous answer's card stays on screen.
      if (body.card) { renderCards(cardsFromBody(body)); }
    }, function (message) {
      pending.remove();
      addBubble("Sorry — " + message, "assistant error");
    });
  });

  correctBtn.addEventListener("click", function () {
    var correction = window.prompt(
      "What should be corrected about the last answer?" +
      (lastQuestion ? "\n(Last question: " + lastQuestion + ")" : ""));
    if (!correction) { return; }
    addBubble("That answer is wrong: " + correction, "user");
    var pending = postJson("/api/correct", { correction: correction }, function (body) {
      pending.remove();
      addBubble(body.spoken || "Correction noted.", "assistant");
      speak(body.spoken || "");
    }, function (message) {
      pending.remove();
      addBubble("Sorry — " + message, "assistant error");
    });
  });

  // ---- Push-to-talk via the Web Speech API (optional; typing always works)
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    micBtn.disabled = true;
    if (hint.textContent === "Initializing...") {
      hint.textContent = "This browser has no Web Speech API; type your questions instead. Everything else works the same.";
    }
  } else {
    micBtn.disabled = false;
    var recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    var listening = false;

    micBtn.addEventListener("click", function () {
      if (listening) { recognition.stop(); return; }
      try {
        recognition.start();
        listening = true;
        micBtn.classList.add("listening");
        micBtn.textContent = "Listening… (click to stop)";
      } catch (err) { /* already started */ }
    });

    recognition.addEventListener("result", function (ev) {
      var transcript = ev.results[0][0].transcript;
      ask(transcript.trim());
    });

    function stopListening() {
      listening = false;
      micBtn.classList.remove("listening");
      micBtn.textContent = "Push to talk";
    }
    recognition.addEventListener("end", stopListening);
    recognition.addEventListener("error", stopListening);
    
    // Update placeholder text to indicate voice input is available
    // (the mic button toggles listening on click; click again to stop).
    textInput.placeholder = "Type a question, or click the mic to talk…";
  }
  
  // Detect mode after setting up speech recognition
  detectMode();
})();
