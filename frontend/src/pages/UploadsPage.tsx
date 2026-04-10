import { useState } from 'react';
import { SectionCard } from '@/components/common/SectionCard';
import { DashboardApi } from '@/services/api';

export function UploadsPage() {
  const [message, setMessage] = useState('');

  const upload = async (event: React.FormEvent<HTMLFormElement>, endpoint: 'learning' | 'offer') => {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    setMessage('Uploading...');
    try {
      const response = endpoint === 'learning' ? await DashboardApi.uploadDocument(formData) : await DashboardApi.uploadOffer(formData);
      setMessage(`Success: ${response.message ?? response.preview ?? 'Uploaded successfully'}`);
      form.reset();
    } catch (error) {
      setMessage(`Error: ${String(error)}`);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <SectionCard title="Learning Documents" subtitle="PDF/JPEG/Excel for AI knowledge base">
        <form className="space-y-3" onSubmit={(e) => upload(e, 'learning')}>
          <input name="file" type="file" accept=".pdf,.jpeg,.jpg,.png,.xls,.xlsx" required className="w-full text-sm" />
          <select name="doc_type" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm">
            <option value="pricing">Pricing</option><option value="offer">Offer</option><option value="brochure">Brochure</option><option value="competitor">Competitor</option>
          </select>
          <button className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white">Upload for Learning</button>
        </form>
      </SectionCard>
      <SectionCard title="Offer Upload" subtitle="Publish latest schemes and pricing assets">
        <form className="space-y-3" onSubmit={(e) => upload(e, 'offer')}>
          <input name="title" placeholder="Offer title" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" required />
          <input name="valid_till" type="date" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
          <input name="models" placeholder="Applicable models (comma separated)" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" />
          <input name="file" type="file" accept=".pdf,.jpeg,.jpg" required className="w-full text-sm" />
          <button className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white">Upload Offer</button>
        </form>
      </SectionCard>
      {message ? <p className="lg:col-span-2 rounded-xl bg-slate-900 px-4 py-2 text-sm text-white">{message}</p> : null}
    </div>
  );
}
