import React from "react";
import ReactDOM from "react-dom/client";
import { VerificationWizard } from "./features/documentVerification";
import type { VerificationOutput } from "./features/documentVerification";
import "./index.css";

// ─── Django context injected by the template ────────────────────────────────
interface DjangoContext {
  csrfToken: string;
  apiBaseUrl: string;
  existingDocuments: {
    idFront: string;
    idBack: string;
    payslips: string[];
    selfie: string;
  };
  verificationStatus: string;
  confidence: number;
}

const context: DjangoContext = (window as any).VERIFICATION_CONTEXT ?? {
  csrfToken: "",
  apiBaseUrl: "/api/verify",
  existingDocuments: { idFront: "", idBack: "", payslips: [], selfie: "" },
  verificationStatus: "pending",
  confidence: 0,
};

// ─── CSRF helper ────────────────────────────────────────────────────────────
function getCsrfToken(): string {
  // 1. Window context (injected by Django template)
  if (context.csrfToken) return context.csrfToken;
  // 2. Meta tag fallback
  const meta = document.querySelector<HTMLMetaElement>(
    'meta[name="csrf-token"]',
  );
  if (meta?.content) return meta.content;
  // 3. Cookie fallback
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : "";
}

// ─── API helpers ─────────────────────────────────────────────────────────────

async function uploadDocuments(output: VerificationOutput): Promise<void> {
  const formData = new FormData();
  const { documents } = output.clientData;

  if (documents.idFront?.file)
    formData.append("id_front", documents.idFront.file);
  if (documents.idBack?.file) formData.append("id_back", documents.idBack.file);
  documents.payslips.forEach((file, i) =>
    formData.append(`payslip_${i}`, file),
  );
  if (documents.selfie) formData.append("selfie", documents.selfie);

  // Include verification results so server can validate client-side checks passed
  formData.append("verification_data", JSON.stringify({
    verification: output.verification,
    summary: output.summary,
  }));

  const res = await fetch(`${context.apiBaseUrl}/documents/upload/`, {
    method: "POST",
    headers: { "X-CSRFToken": getCsrfToken() },
    credentials: "same-origin",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: "Upload failed" }));
    throw new Error(err.error ?? `Upload failed (HTTP ${res.status})`);
  }
}

async function updateProfile(output: VerificationOutput): Promise<void> {
  const { clientData, verification, summary } = output;

  const body = {
    extracted_data: {
      personalInfo: {
        idNumber: clientData.idNumber,
        dateOfBirth: clientData.dateOfBirth,
        gender: clientData.gender,
        fullName: clientData.fullName,
      },
      employmentInfo: {
        employer: clientData.employer,
        monthlyIncome: clientData.monthlyIncome,
      },
    },
    verification_results: verification,
    confidence_score: summary.confidenceScore,
  };

  const res = await fetch(`${context.apiBaseUrl}/profile/update/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res
      .json()
      .catch(() => ({ error: "Profile update failed" }));
    throw new Error(err.error ?? `Profile update failed (HTTP ${res.status})`);
  }
}

async function submitVerification(
  output: VerificationOutput,
): Promise<{ odoo_synced: boolean }> {
  const res = await fetch(`${context.apiBaseUrl}/submit/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    credentials: "same-origin",
    body: JSON.stringify({ confidence_score: output.summary.confidenceScore }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: "Submission failed" }));
    throw new Error(err.error ?? `Submission failed (HTTP ${res.status})`);
  }
  return res.json();
}

// ─── Auto-fill Django form fields ────────────────────────────────────────────

function autoFillForm(output: VerificationOutput): void {
  const { clientData } = output;

  const fieldMap: Record<string, string | number> = {
    id_id_number: clientData.idNumber ?? "",
    id_date_of_birth: clientData.dateOfBirth ?? "",
    id_employer_name: clientData.employer ?? "",
    id_monthly_income: clientData.monthlyIncome ?? "",
  };

  Object.entries(fieldMap).forEach(([id, value]) => {
    const el = document.getElementById(id) as
      | HTMLInputElement
      | HTMLSelectElement
      | null;
    if (el && value) {
      el.value = String(value);
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
  });

  // Store verification output in the hidden input so the Django form posts it
  const hidden = document.getElementById(
    "verification-data",
  ) as HTMLInputElement | null;
  if (hidden) hidden.value = JSON.stringify(output);
}

// ─── Completion handler ──────────────────────────────────────────────────────

async function handleComplete(output: VerificationOutput): Promise<void> {
  try {
    // Step 1 — Upload files to Django media storage
    await uploadDocuments(output);

    // Step 2 — Write extracted OCR data back to Customer record
    await updateProfile(output);

    // Step 3 — Mark verified + trigger Odoo KYC sync
    const { odoo_synced } = await submitVerification(output);

    // Step 4 — Auto-fill the profile form fields
    autoFillForm(output);

    // Step 5 — Show success banner
    const banner = document.getElementById("success-banner");
    if (banner) {
      banner.classList.add("show");
      banner.querySelector(".success-banner-text")!.textContent =
        `Documents validated and submitted for KYC review.${odoo_synced ? " Synced to review team." : ""} Form fields auto-filled.`;
    }

    // Step 6 — Notify any other Django listeners
    window.dispatchEvent(
      new CustomEvent("verificationComplete", { detail: output }),
    );

    // Scroll to top so user sees the success banner
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (err) {
    console.error("Verification submission error:", err);
    window.dispatchEvent(
      new CustomEvent("verificationError", {
        detail: { message: (err as Error).message },
      }),
    );
    // Surface error to user
    const banner = document.getElementById("success-banner");
    if (banner) {
      banner.style.background = "#fef2f2";
      banner.style.borderColor = "#fca5a5";
      banner.classList.add("show");
      const textEl = banner.querySelector(".success-banner-text");
      if (textEl) {
        textEl.textContent = `Verification failed: ${(err as Error).message}`;
        (textEl as HTMLElement).style.color = "#991b1b";
      }
    }
  }
}

// ─── Mount ──────────────────────────────────────────────────────────────────

const rootEl = document.getElementById("verification-root");

if (rootEl) {
  ReactDOM.createRoot(rootEl).render(
    <React.StrictMode>
      <VerificationWizard
        onComplete={handleComplete}
        onCancel={() =>
          window.dispatchEvent(new CustomEvent("verificationCancelled"))
        }
      />
    </React.StrictMode>,
  );
} else {
  console.error("[Alba] #verification-root element not found in DOM.");
}
