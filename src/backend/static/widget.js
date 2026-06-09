(function() {
    console.log("OpenTicket Monospace Widget Initialized");
    
    // Find widget container on the host page
    const container = document.getElementById("openticket-widget");
    if (!container) return;

    // Read parameters from data attributes
    const eventId = container.getAttribute("data-event-id");
    const apiUrl = container.getAttribute("data-api-url") || window.location.origin;

    if (!eventId) {
        container.innerHTML = `<div style="font-family: monospace; color: red; padding: 10px; border: 1px solid red;">Error: data-event-id is required on the widget container.</div>`;
        return;
    }

    // Main initialization flow
    initWidget();

    async function initWidget() {
        try {
            // 1. Fetch Branding Config & Event Tiers in parallel
            const [configRes, eventRes] = await Promise.all([
                fetch(`${apiUrl}/api/widget/config`),
                fetch(`${apiUrl}/api/events/${eventId}`)
            ]);

            if (!eventRes.ok) throw new Error("Failed to load event details.");
            
            const config = await configRes.json();
            const event = await eventRes.json();

            // 2. Setup dynamic styling variables
            const primaryColor = config.primary_color || "#ffffff";
            const accentColor = config.accent_color || "#ff0055";

            // Inject scoped CSS
            const styleId = "openticket-widget-styles";
            if (!document.getElementById(styleId)) {
                const styleEl = document.createElement("style");
                styleEl.id = styleId;
                styleEl.textContent = `
                    .ot-container {
                        font-family: monospace, Courier, monospace;
                        background-color: #111111;
                        color: #ffffff;
                        border: 2px solid ${primaryColor};
                        padding: 20px;
                        max-width: 450px;
                        box-sizing: border-box;
                    }
                    .ot-title {
                        color: ${accentColor};
                        margin-top: 0;
                        margin-bottom: 8px;
                        font-size: 22px;
                        text-transform: uppercase;
                    }
                    .ot-meta {
                        font-size: 13px;
                        color: #888888;
                        margin-bottom: 20px;
                        border-bottom: 1px dashed #333333;
                        padding-bottom: 10px;
                    }
                    .ot-tier-row {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 15px;
                        padding: 10px;
                        background-color: #1a1a1a;
                        border: 1px solid #333333;
                    }
                    .ot-tier-info h4 {
                        margin: 0;
                        font-size: 16px;
                    }
                    .ot-tier-info span {
                        font-size: 12px;
                        color: #888888;
                    }
                    .ot-qty-selector {
                        background-color: #000000;
                        color: #ffffff;
                        border: 1px solid ${primaryColor};
                        font-family: monospace;
                        padding: 5px;
                    }
                    .ot-button {
                        background-color: ${accentColor};
                        color: #ffffff;
                        border: none;
                        font-family: monospace;
                        font-weight: bold;
                        padding: 10px 15px;
                        width: 100%;
                        cursor: pointer;
                        text-transform: uppercase;
                        margin-top: 15px;
                    }
                    .ot-button:hover {
                        opacity: 0.9;
                    }
                    .ot-button:disabled {
                        background-color: #444444;
                        color: #888888;
                        cursor: not-allowed;
                    }
                    .ot-error {
                        color: #ff0055;
                        font-size: 12px;
                        margin-top: 10px;
                        border: 1px solid #ff0055;
                        padding: 8px;
                        display: none;
                    }
                    .ot-loading {
                        text-align: center;
                        color: #888888;
                        padding: 20px;
                    }
                    .ot-tier-status {
                        font-size: 12px;
                        color: #888888;
                        border: 1px solid #333333;
                        padding: 3px 6px;
                        background-color: #0d0d0d;
                    }
                `;
                document.head.appendChild(styleEl);
            }

            // 3. Render Widget HTML structure
            let tiersHtml = "";
            let hasAnyAvailable = false;
            const currency = config.currency || "USD";
            const currencySymbols = {
                "USD": "$",
                "EUR": "€",
                "GBP": "£",
                "CZK": " Kč"
            };
            const symbol = currencySymbols[currency] || "$";

            if (event.tiers && event.tiers.length > 0) {
                event.tiers.forEach(tier => {
                    const now = new Date();
                    let isPaused = !tier.is_active;
                    
                    let hasNotStarted = false;
                    if (tier.sales_start_at) {
                        const startAt = new Date(tier.sales_start_at);
                        if (now < startAt) {
                            hasNotStarted = true;
                        }
                    }
                    
                    let hasEnded = false;
                    if (tier.sales_end_at) {
                        const endAt = new Date(tier.sales_end_at);
                        if (now > endAt) {
                            hasEnded = true;
                        }
                    }

                    let priceStr = "";
                    if (currency === "CZK") {
                        priceStr = `${tier.price.toFixed(2)} Kč`;
                    } else {
                        priceStr = `${symbol}${tier.price.toFixed(2)}`;
                    }

                    let controlHtml = "";
                    if (!isPaused && !hasNotStarted && !hasEnded) {
                        hasAnyAvailable = true;
                        controlHtml = `
                            <select class="ot-qty-selector" data-tier-id="${tier.id}">
                                <option value="0">0</option>
                                <option value="1">1</option>
                                <option value="2">2</option>
                                <option value="3">3</option>
                                <option value="4">4</option>
                                <option value="5">5</option>
                            </select>
                        `;
                    } else {
                        let statusText = "";
                        if (isPaused) {
                            statusText = "Sales paused";
                        } else if (hasNotStarted) {
                            const startStr = new Date(tier.sales_start_at).toLocaleString(undefined, {
                                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                            });
                            statusText = `Sales start: ${startStr}`;
                        } else if (hasEnded) {
                            statusText = "Sales ended";
                        }
                        controlHtml = `<span class="ot-tier-status">${statusText}</span>`;
                    }

                    tiersHtml += `
                        <div class="ot-tier-row">
                            <div class="ot-tier-info">
                                <h4>${tier.name}</h4>
                                <span>${priceStr}</span>
                            </div>
                            <div>
                                ${controlHtml}
                            </div>
                        </div>
                    `;
                });
            } else {
                tiersHtml = `<div style="color: #888888; font-size: 13px;">No tickets currently available for this event.</div>`;
            }

            const dateStr = new Date(event.date).toLocaleString(undefined, {
                year: 'numeric', month: 'short', day: 'numeric',
                hour: '2-digit', minute: '2-digit'
            });

            container.innerHTML = `
                <div class="ot-container">
                    <h3 class="ot-title">${event.name}</h3>
                    <div class="ot-meta">
                        <div>LOCATION: ${event.location}</div>
                        <div>DATE: ${dateStr}</div>
                    </div>
                    <div id="ot-tiers-list">
                        ${tiersHtml}
                    </div>
                    <div id="ot-error-msg" class="ot-error"></div>
                    ${hasAnyAvailable ? `<button id="ot-checkout-btn" class="ot-button">CHECKOUT TICKETS</button>` : ''}
                </div>
            `;

            // 4. Bind event listeners
            const checkoutBtn = document.getElementById("ot-checkout-btn");
            if (checkoutBtn) {
                checkoutBtn.addEventListener("click", () => handleCheckout(eventId, apiUrl));
            }

        } catch (err) {
            console.error("OpenTicket Widget Error:", err);
            container.innerHTML = `<div style="font-family: monospace; color: #ff0055; padding: 10px; border: 1px solid #ff0055;">Error loading booking widget: ${err.message}</div>`;
        }
    }

    async function handleCheckout(eventId, apiUrl) {
        const errorMsg = document.getElementById("ot-error-msg");
        const checkoutBtn = document.getElementById("ot-checkout-btn");
        
        errorMsg.style.display = "none";
        errorMsg.innerText = "";
        
        // Find selected tier and quantity
        const selectors = document.querySelectorAll(".ot-qty-selector");
        let selectedTierId = null;
        let selectedQty = 0;

        selectors.forEach(select => {
            const val = parseInt(select.value);
            if (val > 0) {
                selectedTierId = parseInt(select.getAttribute("data-tier-id"));
                selectedQty = val;
            }
        });

        if (!selectedTierId || selectedQty === 0) {
            errorMsg.innerText = "Please select at least 1 ticket.";
            errorMsg.style.display = "block";
            return;
        }

        try {
            checkoutBtn.disabled = true;
            checkoutBtn.innerText = "Reserving...";

            // Step 1: Create local reservation
            const reserveRes = await fetch(`${apiUrl}/api/events/${eventId}/reserve`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tier_id: selectedTierId,
                    quantity: selectedQty
                })
            });

            const reserveData = await reserveRes.json();
            if (!reserveRes.ok) {
                throw new Error(reserveData.detail || "Ticket reservation failed.");
            }

            const bookingSessionId = reserveData.id;
            checkoutBtn.innerText = "Redirecting...";

            // Redirect user to the internal checkout page
            window.location.href = `/checkout/${bookingSessionId}`;

        } catch (err) {
            console.error("Checkout flow failed:", err);
            errorMsg.innerText = err.message;
            errorMsg.style.display = "block";
            checkoutBtn.disabled = false;
            checkoutBtn.innerText = "CHECKOUT TICKETS";
        }
    }
})();
