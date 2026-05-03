export default function ServicePhotoArchitectureDiagram() {
  const Box = ({ title, children, className = "" }) => (
    <div className={`rounded-2xl border border-slate-300 bg-white shadow-sm p-4 ${className}`}>
      <div className="text-sm font-semibold text-slate-900 mb-2">{title}</div>
      <div className="text-xs text-slate-700 leading-5">{children}</div>
    </div>
  );

  const Arrow = ({ label }) => (
    <div className="flex items-center justify-center gap-2 text-slate-500 text-xs font-medium">
      <div className="h-px flex-1 bg-slate-300" />
      {label && <span className="whitespace-nowrap">{label}</span>}
      <div className="h-px flex-1 bg-slate-300" />
      <span>→</span>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900">Service Photo POC — System Architecture</h1>
          <p className="text-slate-600 mt-2 text-sm">
            Human-in-the-loop used-camera listing workflow built around image upload, Gemini extraction, manual review, and CSV export.
          </p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-5 gap-4 items-start">
          <Box title="1. Store User" className="xl:col-span-1">
            Uploads product photos for one used item, starts analysis, reviews AI output, edits fields, and approves final listing data.
          </Box>

          <Box title="2. Review App / Shell UI" className="xl:col-span-1">
            <ul className="list-disc ml-4 space-y-1">
              <li>Image upload</li>
              <li>Job creation</li>
              <li>Photo preview</li>
              <li>Review/edit extracted fields</li>
              <li>Approve and export</li>
            </ul>
          </Box>

          <Box title="3. Backend Orchestrator" className="xl:col-span-1">
            <ul className="list-disc ml-4 space-y-1">
              <li>Validates uploads</li>
              <li>Creates listing job</li>
              <li>Builds Gemini request payload</li>
              <li>Validates AI response</li>
              <li>Maps approved output to CSV schema</li>
            </ul>
          </Box>

          <Box title="4. Gemini API / AI Extraction" className="xl:col-span-1">
            <ul className="list-disc ml-4 space-y-1">
              <li>Analyzes item photos</li>
              <li>Extracts visible product details</li>
              <li>Drafts title and description</li>
              <li>Flags uncertainty / missing info</li>
              <li>Returns structured JSON draft</li>
            </ul>
          </Box>

          <Box title="5. Export Output" className="xl:col-span-1">
            <ul className="list-disc ml-4 space-y-1">
              <li>Approved listing record</li>
              <li>CSV export file</li>
              <li>Archived job data</li>
              <li>Optional audit / logs</li>
            </ul>
          </Box>
        </div>

        <div className="mt-4 grid grid-cols-1 xl:grid-cols-5 gap-4">
          <div className="xl:col-span-1"><Arrow label="Uploads photos" /></div>
          <div className="xl:col-span-1"><Arrow label="Sends job" /></div>
          <div className="xl:col-span-1"><Arrow label="Requests analysis" /></div>
          <div className="xl:col-span-1"><Arrow label="Returns draft JSON" /></div>
          <div className="xl:col-span-1"><Arrow label="Exports approved CSV" /></div>
        </div>

        <div className="mt-10 grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Box title="Data Stored During Flow">
            <ul className="list-disc ml-4 space-y-1">
              <li>Uploaded image files</li>
              <li>Job metadata and status</li>
              <li>Raw Gemini response</li>
              <li>Validated structured output</li>
              <li>User-corrected listing data</li>
              <li>Final CSV export</li>
            </ul>
          </Box>

          <Box title="Primary Workflow States">
            <div className="space-y-1">
              <div>Uploaded</div>
              <div>Initialized</div>
              <div>Submitted to AI</div>
              <div>Ready for Review</div>
              <div>Approved</div>
              <div>Exported</div>
            </div>
          </Box>

          <Box title="Key Controls">
            <ul className="list-disc ml-4 space-y-1">
              <li>Human review required before export</li>
              <li>Editable fields override AI output</li>
              <li>Low-confidence values visibly flagged</li>
              <li>Structured-first JSON response</li>
              <li>CSV schema validated before final export</li>
            </ul>
          </Box>
        </div>

        <div className="mt-10 rounded-2xl border border-slate-300 bg-white shadow-sm p-6">
          <div className="text-sm font-semibold text-slate-900 mb-4">Architecture Flow</div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-700">
            <div className="rounded-full border border-slate-300 px-3 py-2 bg-slate-50">Store Employee</div>
            <span>→</span>
            <div className="rounded-full border border-slate-300 px-3 py-2 bg-slate-50">Upload Photos</div>
            <span>→</span>
            <div className="rounded-full border border-slate-300 px-3 py-2 bg-slate-50">Create Listing Job</div>
            <span>→</span>
            <div className="rounded-full border border-slate-300 px-3 py-2 bg-slate-50">Backend Orchestrator</div>
            <span>→</span>
            <div className="rounded-full border border-slate-300 px-3 py-2 bg-slate-50">Gemini Analysis</div>
            <span>→</span>
            <div className="rounded-full border border-slate-300 px-3 py-2 bg-slate-50">Review + Edit</div>
            <span>→</span>
            <div className="rounded-full border border-slate-300 px-3 py-2 bg-slate-50">Approve</div>
            <span>→</span>
            <div className="rounded-full border border-slate-300 px-3 py-2 bg-slate-50">CSV Export</div>
          </div>
        </div>
      </div>
    </div>
  );
}
