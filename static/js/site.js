(function () {
  "use strict";
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var finePointer = window.matchMedia("(pointer: fine)").matches;

  function csrfToken(form) {
    var input = form.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : "";
  }

  // ------------------------------------------------------------ reveal
  var items = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.1, rootMargin: "0px 0px -30px 0px" });
    items.forEach(function (el) { io.observe(el); });
  } else {
    items.forEach(function (el) { el.classList.add("in"); });
  }

  // ----------------------------------------------------------- filters
  var chips = document.querySelectorAll(".filters .chip");
  var cards = document.querySelectorAll(".pitem");
  function applyFilter(cat) {
    chips.forEach(function (c) { c.classList.toggle("active", c.dataset.filter === cat); });
    cards.forEach(function (card) {
      var show = cat === "all" || card.dataset.cat === cat;
      card.classList.toggle("hide", !show);
      if (show) card.classList.add("in");
    });
  }
  if (chips.length) {
    chips.forEach(function (c) {
      c.addEventListener("click", function () { applyFilter(c.dataset.filter); });
    });
    var wanted = new URLSearchParams(location.search).get("cat");
    if (wanted && document.querySelector('.filters .chip[data-filter="' + wanted + '"]')) applyFilter(wanted);
  }
  document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { el.form.submit(); });
  });
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });

  // ---------------------------------------------------------- quantity
  document.querySelectorAll("[data-qty]").forEach(function (box) {
    var input = box.querySelector("input");
    var min = parseInt(input.min, 10) || 1;
    var max = parseInt(input.max, 10) || 10;
    function clamp() {
      var v = parseInt(input.value, 10) || min;
      input.value = Math.max(min, Math.min(max, v));
    }
    box.querySelectorAll("[data-step]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        input.value = (parseInt(input.value, 10) || min) + parseInt(btn.dataset.step, 10);
        clamp();
        var form = input.closest("form[data-auto-submit]");
        if (form) form.submit();
      });
    });
    input.addEventListener("change", function () {
      clamp();
      var form = input.closest("form[data-auto-submit]");
      if (form) form.submit();
    });
  });

  // ------------------------------------------------------------- toast
  var toast = document.getElementById("cartToast");
  var toastTimer;
  function showToast(msg, withCartLink) {
    if (!toast) return;
    toast.querySelector("[data-toast-msg]").textContent = msg;
    var link = toast.querySelector("[data-toast-link]");
    if (link) link.hidden = withCartLink === false;
    toast.hidden = false;
    requestAnimationFrame(function () { toast.classList.add("show"); });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toast.classList.remove("show");
      setTimeout(function () { toast.hidden = true; }, 300);
    }, 3500);
  }
  function setCount(n) {
    document.querySelectorAll("[data-cart-count]").forEach(function (el) { el.textContent = n; el.hidden = !n; });
    var link = document.querySelector(".cart-link");
    if (link) { link.classList.remove("bump"); void link.offsetWidth; link.classList.add("bump"); }
  }
  function postJSON(form, submitter) {
    return fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrfToken(form) },
      credentials: "same-origin"
    }).then(function (r) { return r.json().then(function (data) { return { status: r.status, data: data }; }); });
  }

  // Add to cart without leaving the page (falls back to a normal post)
  document.querySelectorAll("form[data-add-cart]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (e.submitter && e.submitter.name === "next") return; // "Buy now" posts normally
      if (!window.fetch) return;
      e.preventDefault();
      var btn = e.submitter || form.querySelector('button[type="submit"]');
      if (btn) btn.disabled = true;
      postJSON(form).then(function (res) {
        if (res.data.ok) setCount(res.data.count);
        showToast(res.data.message || "Done", true);
      }).catch(function () { form.submit(); }).finally(function () { if (btn) btn.disabled = false; });
    });
  });

  // Wishlist hearts
  document.querySelectorAll("form[data-wishlist]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.fetch) return;
      e.preventDefault();
      postJSON(form).then(function (res) {
        if (res.status === 401) {
          if (window.openAuth) window.openAuth("login", location.pathname + location.search);
          else window.location.href = "/account/login/?next=" + encodeURIComponent(location.pathname);
          return;
        }
        var btn = form.querySelector("button");
        var saved = !!res.data.saved;
        btn.classList.toggle("on", saved);
        btn.setAttribute("aria-pressed", saved ? "true" : "false");
        var icon = btn.querySelector("i");
        if (icon) icon.className = "bi " + (saved ? "bi-heart-fill" : "bi-heart");
        var label = btn.querySelector("span");
        if (label) label.textContent = saved ? "Saved" : "Save";
        showToast(res.data.message || "Updated", false);
      }).catch(function () { form.submit(); });
    });
  });

  // ----------------------------------------------------------- gallery
  var gallery = document.querySelector("[data-gallery]");
  if (gallery) {
    var thumbs = Array.prototype.slice.call(gallery.querySelectorAll(".g-thumb"));
    var main = document.getElementById("gMain");
    var frame = gallery.querySelector(".g-main");
    var counter = gallery.querySelector("[data-g-count]");
    var current = 0;
    function show(i) {
      current = (i + thumbs.length) % thumbs.length;
      var t = thumbs[current];
      main.src = t.dataset.src;
      main.alt = t.dataset.alt;
      main.className = "fit-" + t.dataset.fit;
      thumbs.forEach(function (b, idx) { b.classList.toggle("active", idx === current); });
      if (counter) counter.textContent = (current + 1) + " / " + thumbs.length;
      t.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
    thumbs.forEach(function (t, i) {
      t.addEventListener("click", function () { show(i); });
      t.addEventListener("mouseenter", function () { if (finePointer) show(i); });
    });
    // hover zoom (desktop pointers only)
    if (finePointer && !reduce) {
      frame.addEventListener("mousemove", function (e) {
        var r = frame.getBoundingClientRect();
        frame.style.setProperty("--zx", ((e.clientX - r.left) / r.width * 100) + "%");
        frame.style.setProperty("--zy", ((e.clientY - r.top) / r.height * 100) + "%");
        frame.classList.add("zooming");
      });
      frame.addEventListener("mouseleave", function () { frame.classList.remove("zooming"); });
    }
    // lightbox
    var lbEl = document.getElementById("lightbox");
    if (lbEl && window.bootstrap) {
      var lb = new bootstrap.Modal(lbEl);
      var lbImg = document.getElementById("lbImg");
      function lbShow(i) { show(i); lbImg.src = thumbs[current].dataset.src; lbImg.alt = thumbs[current].dataset.alt; }
      document.querySelectorAll("[data-lightbox-open]").forEach(function (b) {
        b.addEventListener("click", function (e) { e.stopPropagation(); lbShow(current); lb.show(); });
      });
      frame.addEventListener("click", function () { if (!finePointer) { lbShow(current); lb.show(); } });
      lbEl.querySelector(".lb-prev").addEventListener("click", function () { lbShow(current - 1); });
      lbEl.querySelector(".lb-next").addEventListener("click", function () { lbShow(current + 1); });
      lbEl.addEventListener("keydown", function (e) {
        if (e.key === "ArrowLeft") lbShow(current - 1);
        if (e.key === "ArrowRight") lbShow(current + 1);
      });
    }
  }

  // --------------------------------------------- section nav scroll-spy
  var pdNav = document.getElementById("pdNav");
  if (pdNav && window.bootstrap) {
    new bootstrap.ScrollSpy(document.body, { target: "#pdNav", rootMargin: "-160px 0px -60% 0px", smoothScroll: false });
  }

  // ------------------------------------------------------ pincode check
  var pinBox = document.querySelector("[data-pin-check]");
  if (pinBox) {
    var pinInput = pinBox.querySelector("input");
    var pinBtn = pinBox.querySelector("button");
    var pinOut = pinBox.querySelector(".pin-result");
    try { var saved = localStorage.getItem("cl_pin"); if (saved) pinInput.value = saved; } catch (e) {}
    function checkPin() {
      var pin = pinInput.value.replace(/\D/g, "");
      pinInput.value = pin;
      pinOut.className = "pin-result";
      if (pin.length !== 6) { pinOut.textContent = "Please enter a valid 6-digit PIN code."; pinOut.classList.add("bad"); return; }
      pinBtn.disabled = true;
      fetch(pinBox.dataset.url + "?pin=" + pin, { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          pinOut.textContent = d.message;
          pinOut.classList.add(d.ok ? "ok" : "bad");
          if (d.ok) { try { localStorage.setItem("cl_pin", pin); } catch (e) {} }
        })
        .catch(function () { pinOut.textContent = "Could not check right now. Please try again."; pinOut.classList.add("bad"); })
        .finally(function () { pinBtn.disabled = false; });
    }
    pinBtn.addEventListener("click", checkPin);
    pinInput.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); checkPin(); } });
  }

  // ------------------------------------------------------------- share
  document.querySelectorAll("[data-share]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var data = { title: btn.dataset.title, url: location.href.split("#")[0] };
      if (navigator.share) { navigator.share(data).catch(function () {}); return; }
      if (navigator.clipboard) {
        navigator.clipboard.writeText(data.url).then(function () { showToast("Link copied to clipboard.", false); });
      }
    });
  });

  // ------------------------------------------------ saved address picker
  var picks = document.querySelectorAll(".addr-pick");
  if (picks.length) {
    var form = document.getElementById("checkoutForm");
    picks.forEach(function (btn) {
      btn.addEventListener("click", function () {
        picks.forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        ["name", "phone", "address", "city", "state", "pincode"].forEach(function (f) {
          var field = form.querySelector('[name="' + f + '"]');
          if (field) field.value = btn.dataset[f] || "";
        });
      });
    });
  }

  // ----------------------------------------------------- review stars
  var reviewForm = document.querySelector("[data-review-form]");
  if (reviewForm) {
    var stars = reviewForm.querySelectorAll(".star-input button");
    var ratingField = reviewForm.querySelector('[name="rating"]');
    function paint(v) {
      stars.forEach(function (s) {
        var on = parseInt(s.dataset.value, 10) <= v;
        s.classList.toggle("on", on);
        s.querySelector("i").className = "bi " + (on ? "bi-star-fill" : "bi-star");
      });
    }
    paint(parseInt(ratingField.value, 10) || 0);
    stars.forEach(function (s) {
      s.addEventListener("click", function () { ratingField.value = s.dataset.value; paint(parseInt(s.dataset.value, 10)); });
    });
    reviewForm.addEventListener("submit", function (e) {
      if (!ratingField.value) { e.preventDefault(); showToast("Please choose a star rating first.", false); }
    });
  }

  // ------------------------------------------------------ password UI
  document.querySelectorAll("[data-pw-toggle]").forEach(function (btn) {
    var input = btn.parentElement.querySelector("input");
    btn.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", show ? "true" : "false");
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      btn.querySelector("i").className = "bi " + (show ? "bi-eye-slash" : "bi-eye");
      input.focus();
    });
  });

  document.querySelectorAll("[data-pw-meter]").forEach(function (meter) {
    var input = document.getElementById(meter.dataset.target);
    if (!input) return;
    var rules = meter.parentElement.querySelector("[data-pw-rules]");
    var label = meter.querySelector(".pw-label");
    var names = ["Password strength", "Too weak", "Weak", "Good", "Strong"];
    function evaluate() {
      var v = input.value;
      var checks = {
        len: v.length >= 8,
        mix: /[A-Za-z]/.test(v) && /\d/.test(v),
        "case": /[a-z]/.test(v) && /[A-Z]/.test(v),
        sym: /[^A-Za-z0-9]/.test(v) || v.length >= 12
      };
      var score = v ? Object.keys(checks).filter(function (k) { return checks[k]; }).length : 0;
      if (v && !checks.len) score = Math.min(score, 1);
      meter.dataset.score = score;
      label.textContent = names[score];
      if (rules) rules.querySelectorAll("li").forEach(function (li) { li.classList.toggle("ok", !!checks[li.dataset.rule]); });
    }
    input.addEventListener("input", evaluate);
    evaluate();
  });

  // ------------------------------------------------ newsletter signup
  document.querySelectorAll("form[data-newsletter]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.fetch) return;
      e.preventDefault();
      var btn = form.querySelector("button");
      btn.disabled = true;
      postJSON(form).then(function (res) {
        showToast(res.data.message || "Done", false);
        if (res.data.ok) form.reset();
      }).catch(function () { form.submit(); }).finally(function () { btn.disabled = false; });
    });
  });

  // ------------------------------------------------------ back to top
  var toTop = document.querySelector("[data-to-top]");
  if (toTop) {
    var onScrollTop = function () { toTop.hidden = (window.scrollY || 0) < 700; };
    window.addEventListener("scroll", onScrollTop, { passive: true });
    onScrollTop();
    toTop.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" }); });
  }

  // ------------------------------------------------- shop filters
  var filterForm = document.querySelector("[data-filters]");
  if (filterForm) {
    var wide = window.matchMedia("(min-width: 992px)");
    var timer;
    var submitNow = function () { if (filterForm.requestSubmit) filterForm.requestSubmit(); else filterForm.submit(); };
    var schedule = function () { if (wide.matches) { clearTimeout(timer); timer = setTimeout(submitNow, 550); } };
    filterForm.addEventListener("change", function (e) {
      if (e.target.matches("[data-range-min], [data-range-max], input[type=number]")) return; // handled by the range code
      if (wide.matches) submitNow(); // on mobile the "Show results" button applies everything at once
    });
    // keep the URL clean: do not send empty fields such as min=&max=&type=
    filterForm.addEventListener("submit", function () {
      filterForm.querySelectorAll("input").forEach(function (i) {
        if ((i.type === "number" || i.type === "radio") && i.value === "") i.disabled = true;
      });
    });
    window.addEventListener("pageshow", function () {
      filterForm.querySelectorAll("input:disabled").forEach(function (i) { i.disabled = false; });
    });
    var range = filterForm.querySelector("[data-range]");
    if (range) {
      var lo = parseInt(range.dataset.lo, 10) || 0;
      var hi = parseInt(range.dataset.hi, 10) || lo + 10;
      if (hi <= lo) hi = lo + 10;
      var rMin = range.querySelector("[data-range-min]");
      var rMax = range.querySelector("[data-range-max]");
      var nMin = filterForm.querySelector('input[name="min"]');
      var nMax = filterForm.querySelector('input[name="max"]');
      var fill = range.querySelector(".range-fill");
      var paint = function () {
        fill.style.left = ((+rMin.value - lo) / (hi - lo) * 100) + "%";
        fill.style.right = (100 - (+rMax.value - lo) / (hi - lo) * 100) + "%";
      };
      var fromNumbers = function () {
        rMin.value = nMin.value ? Math.max(lo, Math.min(+nMin.value, hi)) : lo;
        rMax.value = nMax.value ? Math.min(hi, Math.max(+nMax.value, lo)) : hi;
        paint();
      };
      rMin.addEventListener("input", function () { if (+rMin.value > +rMax.value) rMin.value = rMax.value; nMin.value = +rMin.value > lo ? rMin.value : ""; paint(); schedule(); });
      rMax.addEventListener("input", function () { if (+rMax.value < +rMin.value) rMax.value = rMin.value; nMax.value = +rMax.value < hi ? rMax.value : ""; paint(); schedule(); });
      nMin.addEventListener("change", function () { fromNumbers(); schedule(); });
      nMax.addEventListener("change", function () { fromNumbers(); schedule(); });
      fromNumbers();
    }
  }

  // ------------------------------------------- horizontal product rail
  document.querySelectorAll("[data-rail]").forEach(function (rail) {
    var section = rail.closest("section");
    var step = function (dir) {
      var item = rail.querySelector(".rail-item");
      rail.scrollBy({ left: dir * ((item ? item.offsetWidth : 240) + 16) * 2, behavior: reduce ? "auto" : "smooth" });
    };
    var prev = section && section.querySelector("[data-rail-prev]");
    var next = section && section.querySelector("[data-rail-next]");
    if (prev) prev.addEventListener("click", function () { step(-1); });
    if (next) next.addEventListener("click", function () { step(1); });
  });

  // ---------------------------------------------------- hero slider
  var themeHero = document.getElementById("themeCarousel");
  if (themeHero && window.bootstrap) {
    var inst = bootstrap.Carousel.getOrCreateInstance(themeHero, { interval: 6000, ride: "carousel", pause: false, touch: true, wrap: true });
    { inst.cycle(); document.addEventListener("visibilitychange", function () { if (!document.hidden) inst.cycle(); }); }
  }
  var hero = document.getElementById("heroCarousel");
  if (hero && window.bootstrap && reduce) { bootstrap.Carousel.getOrCreateInstance(hero).pause(); }

  // ----------------------------------------- announcement bar rotator
  var announce = document.querySelector("[data-announce]");
  if (announce) {
    var slides = announce.querySelectorAll(".ann");
    if (slides.length > 1 && !reduce) {
      var at = 0;
      setInterval(function () {
        slides[at].classList.remove("on");
        at = (at + 1) % slides.length;
        slides[at].classList.add("on");
      }, 4500);
    }
  }

  // ---------------------------------------------------- sale countdowns
  var countdowns = document.querySelectorAll("[data-countdown]");
  if (countdowns.length) {
    var pad = function (n) { return n < 10 ? "0" + n : "" + n; };
    var tickAll = function () {
      var now = Date.now();
      countdowns.forEach(function (el) {
        var left = Math.floor((new Date(el.dataset.countdown).getTime() - now) / 1000);
        if (isNaN(left)) return;
        if (left <= 0) { el.textContent = "Sale ended"; return; }
        var d = Math.floor(left / 86400), h = Math.floor(left % 86400 / 3600), m = Math.floor(left % 3600 / 60), sec = left % 60;
        el.textContent = (d ? d + "d " : "") + pad(h) + ":" + pad(m) + ":" + pad(sec);
      });
    };
    tickAll();
    setInterval(tickAll, 1000);
  }

  // --------------------------- checkout: button text follows the payment choice
  var payRadios = document.querySelectorAll('#checkoutForm input[name="payment_method"]');
  if (payRadios.length) {
    var placeLabel = document.querySelector('#checkoutForm .summary button[type="submit"] span');
    var syncPay = function () {
      var chosen = document.querySelector('#checkoutForm input[name="payment_method"]:checked');
      if (placeLabel && chosen) placeLabel.textContent = chosen.value === "online" ? "Continue to payment" : "Place order";
    };
    payRadios.forEach(function (r) { r.addEventListener("change", syncPay); });
    syncPay();
  }

  // ------------------------------------- avoid double submits on forms
  ["checkoutForm", "enqForm"].forEach(function (id) {
    var f = document.getElementById(id);
    if (!f) return;
    f.addEventListener("submit", function () {
      var btn = f.querySelector('button[type="submit"]');
      if (btn) { btn.disabled = true; var s = btn.querySelector("span"); if (s) s.textContent = "Please wait..."; }
    });
  });
})();


// ---- cookie notice (essential cookies only, so this is an information banner)
(function () {
  var bar = document.getElementById('cookieBar');
  if (!bar) return;
  var seen = false;
  try { seen = localStorage.getItem('cl_cookie_ok') === '1'; } catch (e) {}
  if (seen) return;
  bar.hidden = false;
  bar.querySelector('[data-cookie-ok]').addEventListener('click', function () {
    try { localStorage.setItem('cl_cookie_ok', '1'); } catch (e) {}
    bar.hidden = true;
  });
})();

// ---- copy-to-clipboard buttons and review "helpful" votes
document.addEventListener('click', function (e) {
  var copy = e.target.closest('[data-copy]');
  if (copy) {
    var field = document.querySelector(copy.getAttribute('data-copy'));
    if (field) {
      field.select();
      var done = function () { copy.textContent = 'Copied'; setTimeout(function () { copy.textContent = 'Copy'; }, 1500); };
      if (navigator.clipboard) { navigator.clipboard.writeText(field.value).then(done); } else { document.execCommand('copy'); done(); }
    }
  }
  var vote = e.target.closest('[data-helpful]');
  if (vote) {
    var token = (document.querySelector('input[name=csrfmiddlewaretoken]') || {}).value || '';
    fetch(vote.getAttribute('data-helpful'), { method: 'POST', headers: { 'X-CSRFToken': token, 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.json().then(function (d) { return [r.status, d]; }); })
      .then(function (res) {
        var d = res[1];
        if (res[0] === 401 && window.openAuth) { window.openAuth(); return; }
        if (d.ok) {
          vote.classList.toggle('on', d.voted);
          vote.querySelector('span').textContent = d.count;
        }
      });
  }
});

// ---- PWA: register the service worker (needs https or localhost) and reload button on the offline page
if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
  window.addEventListener('load', function () { navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {}); });
}
document.addEventListener('click', function (e) { if (e.target.closest('[data-reload]')) location.reload(); });

// ---- print buttons (no inline handlers: the Content-Security-Policy forbids them)
document.addEventListener('click', function (e) {
  if (e.target.closest('[data-print]')) window.print();
});

// ---- search suggestions (typo tolerant, server side)
(function () {
  var form = document.querySelector('.nav-search');
  var input = form && form.querySelector('input[name="q"]');
  if (!input) return;
  var box = document.createElement('div');
  box.className = 'suggest';
  box.hidden = true;
  box.setAttribute('role', 'listbox');
  form.appendChild(box);
  var timer = null, seq = 0, active = -1;

  function esc(t) { var d = document.createElement('div'); d.textContent = t == null ? '' : t; return d.innerHTML; }
  function hide() { box.hidden = true; active = -1; }
  function render(data) {
    if (!data.results.length) { hide(); return; }
    var html = '';
    if (data.corrected) html += '<span class="s-note">Showing results for <b>' + esc(data.corrected) + '</b></span>';
    data.results.forEach(function (r) {
      html += '<a href="' + esc(r.url) + '" role="option"><img src="' + esc(r.image) + '" alt=""><span><b>' + esc(r.name) + '</b><small>' + esc(r.sub) + '</small></span>' +
        (r.price ? '<em>&#8377;' + r.price + '</em>' : '') + '</a>';
    });
    html += '<a class="s-all" href="' + esc(data.all) + '">See all results</a>';
    box.innerHTML = html;
    box.hidden = false;
    active = -1;
  }
  input.addEventListener('input', function () {
    clearTimeout(timer);
    var q = input.value.trim();
    if (q.length < 2) { hide(); return; }
    timer = setTimeout(function () {
      var mine = ++seq;
      fetch('/api/suggest/?q=' + encodeURIComponent(q), { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { return r.json(); })
        .then(function (d) { if (mine === seq) render(d); })
        .catch(hide);
    }, 180);
  });
  input.addEventListener('keydown', function (e) {
    var links = box.querySelectorAll('a');
    if (box.hidden || !links.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      active = (active + (e.key === 'ArrowDown' ? 1 : -1) + links.length) % links.length;
      links.forEach(function (l, i) { l.classList.toggle('active', i === active); });
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault();
      links[active].click();
    } else if (e.key === 'Escape') { hide(); }
  });
  document.addEventListener('click', function (e) { if (!form.contains(e.target)) hide(); });
})();

// ---- distribution network: filter districts by status
(function () {
  var grid = document.getElementById('netGrid');
  if (!grid) return;
  var chips = document.querySelectorAll('[data-net-filter]');
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      var want = chip.getAttribute('data-net-filter');
      chips.forEach(function (c) { c.classList.toggle('on', c === chip); });
      grid.querySelectorAll('.dist-card').forEach(function (t) { t.hidden = want !== 'all' && t.dataset.status !== want; });
    });
  });
})();

// ---- the home hero fills exactly the screen below the fixed header
(function () {
  var header = document.getElementById('siteHeader');
  if (!header) return;
  function setHeaderHeight() { document.documentElement.style.setProperty('--hdr', header.offsetHeight + 'px'); }
  setHeaderHeight();
  window.addEventListener('resize', setHeaderHeight);
  window.addEventListener('load', setHeaderHeight);
})();
