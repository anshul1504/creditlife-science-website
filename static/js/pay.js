/* Opens Razorpay Checkout, then asks our server to verify the payment signature. */
(function () {
  "use strict";
  var configEl = document.getElementById("rz-config");
  if (!configEl) return;
  var cfg = JSON.parse(configEl.textContent);
  var btn = document.getElementById("payBtn");
  var msg = document.getElementById("payMsg");
  var label = btn.querySelector("span");
  var token = document.querySelector("input[name=csrfmiddlewaretoken]").value;

  function say(text, bad) { msg.textContent = text || ""; msg.className = "pay-msg" + (bad ? " bad" : ""); }
  function post(url, data) {
    var body = new URLSearchParams();
    Object.keys(data).forEach(function (k) { body.append(k, data[k] || ""); });
    return fetch(url, { method: "POST", body: body, credentials: "same-origin",
      headers: { "X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/x-www-form-urlencoded" } })
      .then(function (r) { return r.json(); });
  }
  function ready() { btn.disabled = false; label.textContent = "Try again"; }

  function open() {
    if (!window.Razorpay) { say("The payment window could not load. Please check your connection and try again.", true); ready(); return; }
    var rz = new window.Razorpay({
      key: cfg.key, order_id: cfg.order_id, amount: cfg.amount, currency: "INR", name: cfg.name, description: cfg.description,
      prefill: cfg.prefill, theme: { color: "#0E7A55" },
      modal: { ondismiss: function () { say("The payment window was closed. You can try again whenever you are ready."); ready(); } },
      handler: function (response) {
        say("Confirming your payment, please do not close this page...");
        btn.disabled = true;
        post(cfg.verify_url, response).then(function (d) {
          if (d.ok) { window.location.href = d.redirect; } else { say(d.message || "We could not confirm your payment.", true); ready(); }
        }).catch(function () { say("Network problem while confirming. If money was deducted it will be confirmed automatically; check My orders in a minute.", true); ready(); });
      }
    });
    rz.on("payment.failed", function (r) {
      var reason = r && r.error && r.error.description;
      post(cfg.failed_url, { reason: reason });
      say(reason || "The payment failed. Please try again.", true);
      ready();
    });
    btn.disabled = true;
    rz.open();
  }
  btn.addEventListener("click", open);
  window.addEventListener("load", function () { setTimeout(open, 500); });
})();
