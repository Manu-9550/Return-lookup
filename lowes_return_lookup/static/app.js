const form = document.getElementById("lookupForm");
const input = document.getElementById("query");
const loading = document.getElementById("loading");
const error = document.getElementById("error");
const result = document.getElementById("result");

const show = (el) => el.classList.remove("hidden");
const hide = (el) => el.classList.add("hidden");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  hide(error); hide(result); show(loading);

  try {
    const response = await fetch("/api/lookup", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query: input.value.trim()})
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Lookup failed.");

    hide(loading);

    if (!data.found) {
      error.textContent = data.message || "Product not found.";
      show(error);
      return;
    }

    document.getElementById("productName").textContent = data.product_name || "Lowe's product";
    document.getElementById("itemNumber").textContent = data.item_number || "Not found";
    document.getElementById("modelNumber").textContent = data.model_number || "Not found";
    document.getElementById("category").textContent = data.category || "Not detected";
    document.getElementById("timeframe").textContent = data.timeframe;
    document.getElementById("policyCategory").textContent = data.policy_category;
    document.getElementById("reason").textContent = data.reason;

    const notes = document.getElementById("notes");
    notes.textContent = data.notes || "";
    notes.classList.toggle("hidden", !data.notes);

    document.getElementById("productLink").href = data.product_url;
    document.getElementById("policyLink").href = data.policy_url;
    show(result);
  } catch (err) {
    hide(loading);
    error.textContent = err.message || "Something went wrong.";
    show(error);
  }
});
