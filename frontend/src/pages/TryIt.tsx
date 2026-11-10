import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getActivity, getOverview } from "../api";
import { ActivityFeed } from "../components/ActivityFeed";
import { ChatPanel } from "../components/ChatPanel";
import { EnquiryForm } from "../components/EnquiryForm";
import { useAccess } from "../lib/access";
import { setBusinessTz } from "../lib/format";
import { usePoll } from "../lib/hooks";

export default function TryIt() {
  const navigate = useNavigate();
  const { me } = useAccess();
  const overview = usePoll(getOverview, 60000);
  const activity = usePoll(() => getActivity(6), 5000);
  const seen = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());

  useEffect(() => {
    document.title = "MD Cold Services front desk";
  }, []);
  useEffect(() => {
    if (overview.data) setBusinessTz(overview.data.business.tz);
  }, [overview.data]);

  // Items that arrive while the page is open are marked, so a test shows up as it lands.
  useEffect(() => {
    const items = activity.data?.items;
    if (!items) return;
    if (seen.current === null) {
      seen.current = new Set(items.map((i) => i.id));
      return;
    }
    const added = items.filter((i) => !seen.current!.has(i.id)).map((i) => i.id);
    if (added.length) {
      added.forEach((id) => seen.current!.add(id));
      setFresh((f) => new Set([...f, ...added]));
    }
  }, [activity.data]);

  const phone = overview.data?.business.phone ?? "(786) 797-6193";

  return (
    <div className="tryit">
      <section className="intro">
        <h1 className="intro__title">Try the front desk</h1>
        <p className="intro__lede">
          Chat like a homeowner with a broken AC: ask a question, book a technician, then change or cancel it. Or send
          the form and get the answer by email. Every case lands in the office view.
        </p>
        {me?.demo_mode && (
          <p className="intro__demo">
            This is a public demo. Emails are written and shown here instead of being sent, contact details are
            partly hidden in the office, and everything resets each night. Please use made-up details.
          </p>
        )}
      </section>

      <div className="bench">
        <ChatPanel phone={phone} onBooked={() => activity.refresh()} />
        <div className="bench__side">
          <EnquiryForm inbox={overview.data?.business.inbox} onSent={() => activity.refresh()} />
        </div>
      </div>

      <section className="landed" aria-label="Latest in the office">
        <div className="landed__head">
          <h2 className="landed__title">Just landed in the office</h2>
          <button type="button" className="link" onClick={() => navigate("/office")}>See every case</button>
        </div>
        <ActivityFeed
          compact
          items={activity.data?.items ?? null}
          error={activity.error}
          fresh={fresh}
          onCase={(id) => navigate(`/office?case=${id}`)}
        />
      </section>
    </div>
  );
}
