/**
 * Moms Verdict — Frontend Application
 *
 * Handles product grid rendering, category filtering, language toggling,
 * and verdict modal with loading/error/success states.
 */

const API_BASE = '';  // Same origin — FastAPI serves both API and frontend

// ===== STATE =====
let allProducts = [];
let allReviews = [];
let currentCategory = 'all';
let currentLang = 'both';
let currentProductId = null;

// ===== CATEGORY DISPLAY NAMES =====
const CATEGORY_LABELS = {
    car_seats: 'Car Seats',
    strollers: 'Strollers',
    feeding: 'Feeding',
    diapering: 'Diapering',
    nursery: 'Nursery',
    toys: 'Toys',
    bath_skincare: 'Bath & Skincare',
    safety: 'Safety',
    gear: 'Gear',
    mumz: 'For Mumz',
    clothing: 'Clothing',
    outdoor: 'Outdoor',
};

// ===== INITIALIZATION =====
document.addEventListener('DOMContentLoaded', async () => {
    await loadProducts();
    setupFilters();
    setupLangToggle();
    setupModal();
});

// ===== DATA LOADING =====
async function loadProducts() {
    try {
        const resp = await fetch(`${API_BASE}/api/products`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        allProducts = data.products;

        // Load all reviews for review counts
        const reviewsResp = await fetch(`${API_BASE}/api/products`);
        // We'll compute review counts from individual product endpoints
        // For now, render the grid
        renderProducts(allProducts);
        updateStats();
    } catch (err) {
        console.error('Failed to load products:', err);
        document.getElementById('gridContainer').innerHTML =
            '<p style="color:var(--danger);text-align:center;grid-column:1/-1;">Failed to load products. Is the server running?</p>';
    }
}

// Fetch review count for a product (cached)
const reviewCountCache = {};
async function getReviewCount(productId) {
    if (reviewCountCache[productId] !== undefined) return reviewCountCache[productId];
    try {
        const resp = await fetch(`${API_BASE}/api/products/${productId}`);
        const data = await resp.json();
        reviewCountCache[productId] = data.reviews.length;
        return data.reviews.length;
    } catch {
        return 0;
    }
}

// ===== RENDERING =====
async function renderProducts(products) {
    const grid = document.getElementById('gridContainer');
    grid.innerHTML = '';

    for (const product of products) {
        const count = await getReviewCount(product.id);
        const avgRating = count > 0 ? '★'.repeat(4) + '☆' : 'No ratings';

        const card = document.createElement('div');
        card.className = 'product-card';
        card.setAttribute('data-category', product.category);
        card.innerHTML = `
            <span class="card-category">${CATEGORY_LABELS[product.category] || product.category}</span>
            <h3 class="card-name-en">${product.name_en}</h3>
            <p class="card-name-ar">${product.name_ar}</p>
            <div class="card-meta">
                <span class="card-price">${product.price_aed} AED</span>
                <span class="card-age">${product.age_range}</span>
            </div>
            <div class="card-reviews">
                <span class="review-stars">${avgRating}</span>
                <span class="review-count">${count} review${count !== 1 ? 's' : ''}</span>
            </div>
            <button class="card-action" onclick="openVerdict('${product.id}')">
                🔍 Get Mom's Verdict
            </button>
        `;
        grid.appendChild(card);
    }
}

function updateStats() {
    document.getElementById('totalProducts').textContent = allProducts.length;
    // Total reviews will be updated once all counts are loaded
    let total = 0;
    const countPromises = allProducts.map(async (p) => {
        const c = await getReviewCount(p.id);
        total += c;
    });
    Promise.all(countPromises).then(() => {
        document.getElementById('totalReviews').textContent = total;
    });
}

// ===== FILTERING =====
function setupFilters() {
    document.querySelectorAll('.filter-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            currentCategory = chip.dataset.category;
            filterProducts();
        });
    });
}

function filterProducts() {
    const filtered = currentCategory === 'all'
        ? allProducts
        : allProducts.filter(p => p.category === currentCategory);
    renderProducts(filtered);
}

// ===== LANGUAGE TOGGLE =====
function setupLangToggle() {
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentLang = btn.dataset.lang;

            document.body.classList.remove('lang-en', 'lang-ar', 'lang-both');
            document.body.classList.add(`lang-${currentLang}`);
        });
    });
}

// ===== MODAL =====
function setupModal() {
    document.getElementById('modalClose').addEventListener('click', closeModal);
    document.getElementById('verdictModal').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeModal();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });
}

function openModal() {
    document.getElementById('verdictModal').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    document.getElementById('verdictModal').classList.remove('active');
    document.body.style.overflow = '';
}

// ===== VERDICT GENERATION =====
async function openVerdict(productId) {
    currentProductId = productId;
    const product = allProducts.find(p => p.id === productId);
    if (!product) return;

    // Set header
    document.getElementById('modalProductName').textContent = product.name_en;
    document.getElementById('modalProductNameAr').textContent = product.name_ar;

    // Show loading, hide others
    document.getElementById('verdictLoading').style.display = 'block';
    document.getElementById('verdictError').style.display = 'none';
    document.getElementById('verdictInsufficient').style.display = 'none';
    document.getElementById('verdictContent').style.display = 'none';

    openModal();

    // Setup retry button
    document.getElementById('retryBtn').onclick = () => openVerdict(productId);

    try {
        const resp = await fetch(`${API_BASE}/api/verdict`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product_id: productId }),
        });

        const data = await resp.json();
        document.getElementById('verdictLoading').style.display = 'none';

        if (!data.success && data.error) {
            showVerdictError(data.error);
            return;
        }

        if (data.insufficient_data) {
            showInsufficientData(data.insufficient_data);
            return;
        }

        if (data.verdict) {
            showVerdict(data.verdict, data.model_used, data.processing_time_ms);
            return;
        }

        showVerdictError('Unexpected response from server');
    } catch (err) {
        document.getElementById('verdictLoading').style.display = 'none';
        showVerdictError(err.message || 'Network error — is the server running?');
    }
}

function showVerdictError(message) {
    document.getElementById('verdictError').style.display = 'block';
    document.getElementById('errorText').textContent = message;
}

function showInsufficientData(data) {
    document.getElementById('verdictInsufficient').style.display = 'block';
    document.getElementById('insufficientReasonEn').textContent = data.reason_en;
    document.getElementById('insufficientReasonAr').textContent = data.reason_ar;

    const reviewsContainer = document.getElementById('insufficientReviews');
    reviewsContainer.innerHTML = '';
    if (data.available_reviews && data.available_reviews.length > 0) {
        const h4 = document.createElement('h4');
        h4.textContent = `Available Reviews (${data.available_reviews.length}):`;
        h4.style.marginTop = '16px';
        h4.style.marginBottom = '8px';
        reviewsContainer.appendChild(h4);

        data.available_reviews.forEach(r => {
            const div = document.createElement('div');
            div.style.padding = '8px 12px';
            div.style.background = 'rgba(255,255,255,0.03)';
            div.style.borderRadius = '8px';
            div.style.marginBottom = '8px';
            div.style.fontSize = '0.85rem';
            div.style.color = 'var(--text-secondary)';
            if (r.language === 'ar') {
                div.dir = 'rtl';
                div.style.fontFamily = 'var(--font-ar)';
            }
            div.textContent = `${'★'.repeat(r.rating)}${'☆'.repeat(5 - r.rating)} — "${r.text}"`;
            reviewsContainer.appendChild(div);
        });
    }
}

function showVerdict(verdict, modelUsed, processingTimeMs) {
    document.getElementById('verdictContent').style.display = 'block';

    // Score
    document.getElementById('scoreValue').textContent = verdict.overall_score.toFixed(1);
    const scoreCircle = document.getElementById('scoreCircle');
    if (verdict.overall_score >= 4) scoreCircle.style.background = 'linear-gradient(135deg, #34d399, #059669)';
    else if (verdict.overall_score >= 3) scoreCircle.style.background = 'linear-gradient(135deg, #fbbf24, #d97706)';
    else scoreCircle.style.background = 'linear-gradient(135deg, #f87171, #dc2626)';

    // Confidence
    const confPct = Math.round(verdict.confidence * 100);
    document.getElementById('confidenceFill').style.width = `${confPct}%`;
    const confLabel = verdict.confidence >= 0.7 ? 'High' : verdict.confidence >= 0.4 ? 'Medium' : 'Low';
    document.getElementById('confidenceText').textContent = `${confLabel} (${verdict.confidence.toFixed(2)})`;

    // Meta
    document.getElementById('reviewCountBadge').textContent = `📝 ${verdict.review_count} reviews analyzed`;
    document.getElementById('modelBadge').textContent = `🤖 ${(modelUsed || 'AI Model').split('/').pop().replace(':free', '')}`;
    document.getElementById('timeBadge').textContent = `⚡ ${((processingTimeMs || 0) / 1000).toFixed(1)}s`;

    // Safety Flags
    const safetySection = document.getElementById('safetySection');
    const safetyFlags = document.getElementById('safetyFlags');
    if (verdict.safety_flags && verdict.safety_flags.length > 0) {
        safetySection.style.display = 'block';
        safetyFlags.innerHTML = verdict.safety_flags.map(f => `
            <div class="safety-flag-item">
                <span class="safety-severity severity-${f.severity}">${f.severity.toUpperCase()}</span>
                <p class="safety-issue-en">${f.issue_en}</p>
                <p class="safety-issue-ar">${f.issue_ar}</p>
                <p class="safety-quote">"${f.source_quote}"</p>
            </div>
        `).join('');
    } else {
        safetySection.style.display = 'none';
    }

    // Summary
    document.getElementById('summaryEn').textContent = verdict.summary_en;
    document.getElementById('summaryAr').textContent = verdict.summary_ar;

    // Pros
    document.getElementById('prosListEn').innerHTML = (verdict.pros_en || []).map(p => `<li>${p}</li>`).join('');
    document.getElementById('prosListAr').innerHTML = (verdict.pros_ar || []).map(p => `<li>${p}</li>`).join('');

    // Cons
    document.getElementById('consListEn').innerHTML = (verdict.cons_en || []).map(c => `<li>${c}</li>`).join('');
    document.getElementById('consListAr').innerHTML = (verdict.cons_ar || []).map(c => `<li>${c}</li>`).join('');

    // Age Suitability
    const ageCard = document.getElementById('ageSuitabilityCard');
    if (verdict.age_suitability_en) {
        ageCard.style.display = 'block';
        document.getElementById('ageSuitabilityEn').textContent = verdict.age_suitability_en;
        document.getElementById('ageSuitabilityAr').textContent = verdict.age_suitability_ar || '';
    } else {
        ageCard.style.display = 'none';
    }

    // Value for Money
    const valueCard = document.getElementById('valueCard');
    if (verdict.value_for_money) {
        valueCard.style.display = 'block';
        const val = verdict.value_for_money;
        const color = val >= 4 ? 'var(--success)' : val >= 3 ? 'var(--warning)' : 'var(--danger)';
        document.getElementById('valueScore').innerHTML = `<span style="color:${color}">${val.toFixed(1)}</span> <span style="font-size:0.9rem;color:var(--text-muted)">/ 5</span>`;
    } else {
        valueCard.style.display = 'none';
    }

    // Final Verdict
    document.getElementById('verdictTextEn').textContent = verdict.verdict_en;
    document.getElementById('verdictTextAr').textContent = verdict.verdict_ar;

    // Confidence Reasoning
    document.getElementById('confidenceReasoning').textContent = verdict.confidence_reasoning;
}
