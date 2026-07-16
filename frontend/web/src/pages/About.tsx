// About — product identity, authorship, and licensing.
// Surfaces the copyright and licence terms inside the running product so provenance
// is visible to any operator, not only in the repository LICENSE file.
import { PageHeader } from '@/components/PageHeader';
import { Card } from '@/components/Card';

const YEAR = 2026;
const AUTHOR = 'A2Z';

export default function About() {
  return (
    <div className="space-y-4">
      <PageHeader title="About A2Z MIS 360" subtitle="Product identity, authorship, and licence" />

      <Card><Card.Body>
        <div className="space-y-1 text-sm text-gray-700">
          <div className="text-lg font-semibold text-gray-900">A2Z MIS 360</div>
          <div>Enterprise management-information system for retail and commercial banking.</div>
          <div className="pt-2">
            <span className="text-gray-500">Copyright</span> © {YEAR} {AUTHOR}. All rights reserved.
          </div>
          <div>
            <span className="text-gray-500">Author &amp; copyright holder:</span> A2Z
          </div>
        </div>
      </Card.Body></Card>

      <Card><Card.Body>
        <div className="text-sm font-semibold text-gray-900 mb-1">Licence</div>
        <div className="space-y-2 text-sm text-gray-700">
          <p>
            This software is proprietary. It is licensed to <strong>Ecobank Kenya Limited</strong>{' '}
            for its own internal business use as a single legal entity.
          </p>
          <p>
            The licence does not extend to any affiliate, subsidiary, or other entity within the
            Ecobank Transnational Incorporated (ETI) group, nor to deployment at any other national
            operation. Deployment beyond Ecobank Kenya Limited requires a separate written licence
            agreement with the author.
          </p>
          <p className="text-gray-500">
            Full terms are in the repository <code>LICENSE.md</code>. Unauthorised copying,
            redistribution, or deployment is prohibited and may be subject to legal action.
          </p>
        </div>
      </Card.Body></Card>
    </div>
  );
}
