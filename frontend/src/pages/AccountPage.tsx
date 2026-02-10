import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "react-query";
import { deleteAccount } from "../services/api";
import { useAuthStore } from "../store/authStore";

export default function AccountPage() {
  const navigate = useNavigate();
  const clearAuth = useAuthStore((s) => s.clear);
  const [confirmText, setConfirmText] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);

  const deleteMut = useMutation(deleteAccount, {
    onSuccess: () => {
      clearAuth();
      navigate("/login", { replace: true });
    },
  });

  const handleDelete = () => {
    if (confirmText.toLowerCase() !== "delete") return;
    deleteMut.mutate();
  };

  return (
    <div className="mx-auto max-w-xl space-y-8">
      <h1 className="text-2xl font-bold text-slate-800">Account</h1>

      <section className="rounded-xl border border-red-200 bg-red-50/50 p-6">
        <h2 className="mb-2 text-lg font-semibold text-red-800">Delete account</h2>
        <p className="mb-4 text-sm text-red-700">
          This will permanently delete your account and all your data (profile, CV, job matches,
          interview prep, and practice history). This cannot be undone.
        </p>
        {!showConfirm ? (
          <button
            type="button"
            onClick={() => setShowConfirm(true)}
            className="rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
          >
            Delete my account
          </button>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-red-800">
              Type <strong>delete</strong> below to confirm.
            </p>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="delete"
              className="w-full rounded-lg border border-red-300 px-3 py-2 text-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleDelete}
                disabled={confirmText.toLowerCase() !== "delete" || deleteMut.isLoading}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMut.isLoading ? "Deleting…" : "Permanently delete account"}
              </button>
              <button
                type="button"
                onClick={() => { setShowConfirm(false); setConfirmText(""); }}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
            </div>
            {deleteMut.isError && (
              <p className="text-sm text-red-600">
                {(deleteMut.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to delete account."}
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
