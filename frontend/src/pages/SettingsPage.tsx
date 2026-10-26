import React, { useState } from "react";
import { Check } from "lucide-react";

export const SettingsPage: React.FC = () => {
  const [requireReviewerApproval, setRequireReviewerApproval] = useState(true);
  const [skipInternalChanges, setSkipInternalChanges] = useState(true);
  const [emailOnFailedRuns, setEmailOnFailedRuns] = useState(false);
  const [showManageModal, setShowManageModal] = useState(false);
  const [disconnected, setDisconnected] = useState(false);

  return (
    <div className="p-8 lg:p-12 max-w-4xl">
      {/* Title */}
      <h1 className="font-serif text-5xl text-[#F5F2EB] tracking-tight mb-8">
        Settings
      </h1>

      {/* GitHub Connected Card */}
      <div className="border border-[#26231D] bg-[#141310] rounded-xl p-5 flex items-center justify-between mb-8 shadow-sm">
        <div className="flex items-center gap-3.5">
          {/* GitHub Icon */}
          <div className="w-10 h-10 rounded-xl bg-[#0D0C0A] border border-[#26231D] flex items-center justify-center text-[#F5F2EB]">
            <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
              <path
                fillRule="evenodd"
                clipRule="evenodd"
                d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
              />
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-[#F5F2EB]">
              {disconnected ? "GitHub disconnected" : "GitHub connected"}
            </p>
            <p className="font-mono text-xs text-[#8E897F] mt-0.5">
              {disconnected ? "No repositories connected" : "@sujalgawas · 4 repos authorised"}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowManageModal(true)}
          className="border border-[#26231D] bg-[#1F1D18] hover:bg-[#2A2720] text-[#F5F2EB] px-4 py-1.5 rounded-lg text-sm font-sans font-medium transition-colors"
        >
          Manage
        </button>
      </div>

      {/* 3 Policy Toggle Rows */}
      <div className="border border-[#26231D] bg-[#141310] rounded-xl divide-y divide-[#26231D] overflow-hidden mb-8 shadow-sm">
        {/* Row 1 */}
        <div
          onClick={() => setRequireReviewerApproval(!requireReviewerApproval)}
          className="p-5 flex items-center justify-between hover:bg-[#1A1813] transition-colors cursor-pointer select-none"
        >
          <div>
            <p className="text-sm font-medium text-[#F5F2EB]">
              Require reviewer approval
            </p>
            <p className="text-xs text-[#8E897F] mt-0.5">
              Agent PRs need a human thumbs-up before merge.
            </p>
          </div>

          <div
            className={`w-5 h-5 rounded flex items-center justify-center transition-colors shrink-0 ${
              requireReviewerApproval
                ? "bg-accent-orange text-black"
                : "border border-[#3A352C] bg-[#0D0C0A]"
            }`}
          >
            {requireReviewerApproval && <Check className="w-3.5 h-3.5 stroke-[3]" />}
          </div>
        </div>

        {/* Row 2 */}
        <div
          onClick={() => setSkipInternalChanges(!skipInternalChanges)}
          className="p-5 flex items-center justify-between hover:bg-[#1A1813] transition-colors cursor-pointer select-none"
        >
          <div>
            <p className="text-sm font-medium text-[#F5F2EB]">
              Skip internal-only changes
            </p>
            <p className="text-xs text-[#8E897F] mt-0.5">
              Exit early when no public symbol changed.
            </p>
          </div>

          <div
            className={`w-5 h-5 rounded flex items-center justify-center transition-colors shrink-0 ${
              skipInternalChanges
                ? "bg-accent-orange text-black"
                : "border border-[#3A352C] bg-[#0D0C0A]"
            }`}
          >
            {skipInternalChanges && <Check className="w-3.5 h-3.5 stroke-[3]" />}
          </div>
        </div>

        {/* Row 3 */}
        <div
          onClick={() => setEmailOnFailedRuns(!emailOnFailedRuns)}
          className="p-5 flex items-center justify-between hover:bg-[#1A1813] transition-colors cursor-pointer select-none"
        >
          <div>
            <p className="text-sm font-medium text-[#F5F2EB]">
              Email me on failed runs
            </p>
            <p className="text-xs text-[#8E897F] mt-0.5">
              One email, not a flood.
            </p>
          </div>

          <div
            className={`w-5 h-5 rounded flex items-center justify-center transition-colors shrink-0 ${
              emailOnFailedRuns
                ? "bg-accent-orange text-black"
                : "border border-[#3A352C] bg-[#0D0C0A]"
            }`}
          >
            {emailOnFailedRuns && <Check className="w-3.5 h-3.5 stroke-[3]" />}
          </div>
        </div>
      </div>

      {/* Danger Zone Card */}
      <div className="border border-red-900/60 bg-red-950/10 rounded-xl p-6 flex flex-col gap-1.5 shadow-sm">
        <h2 className="text-sm font-semibold text-red-500">
          Disconnect GitHub
        </h2>
        <p className="text-xs text-[#8E897F] mb-3">
          Removes webhooks from every repo. Your docs stay as they are.
        </p>
        <div>
          <button
            type="button"
            onClick={() => setDisconnected(true)}
            className="border border-red-800/80 hover:bg-red-900/20 text-red-400 font-medium px-4 py-1.5 rounded-lg text-sm transition-colors"
          >
            Disconnect
          </button>
        </div>
      </div>

      {/* Manage GitHub Modal */}
      {showManageModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#141310] border border-[#26231D] rounded-2xl w-full max-w-md p-6 shadow-2xl flex flex-col gap-4">
            <h3 className="font-serif text-2xl text-[#F5F2EB]">Manage GitHub App</h3>
            <p className="text-xs font-mono text-[#8E897F] leading-relaxed">
              DocRipple is installed on account <code className="text-[#F5F2EB]">sujalgawas</code> with read access to code and write access to pull requests.
            </p>
            <div className="border border-[#26231D] bg-[#0D0C0A] rounded-lg p-3 font-mono text-xs text-[#8E897F] flex flex-col gap-1">
              <span>• sujalgawas/DocRipple (active)</span>
              <span>• sujalgawas/ledger-api (active)</span>
              <span>• acme-labs/billing-cli (active)</span>
              <span>• acme-labs/design-tokens (paused)</span>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowManageModal(false)}
                className="bg-[#F3EFE6] hover:bg-white text-[#141310] px-4 py-1.5 rounded-lg text-xs font-medium font-sans"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
