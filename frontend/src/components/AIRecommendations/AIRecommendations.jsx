import { useApp } from "../../context/AppContext";
import "./AIRecommendations.css";

export default function AIRecommendations() {
  const { rooms } = useApp();
  const aiPicks = rooms.filter((r) => r.featured && r.available).slice(0, 2);

  return (
    <div className="ai-recommendations">
      <div className="ai-rec-header">
        <span className="ai-rec-icon">🤖</span>
        <div>
          <div className="ai-rec-title">AI Best Matches For You</div>
          <div className="ai-rec-subtitle">Based on Dhanmondi area • ৳10K-20K budget • Studio preference</div>
        </div>
      </div>
      <div className="ai-rec-grid">
        {aiPicks.map((r) => (
          <div key={r.id} className="ai-rec-card">
            <img src={r.img} alt={r.name} className="ai-rec-img" />
            <div className="ai-rec-info">
              <h4>{r.name}</h4>
              <p>৳{r.price.toLocaleString()}/mo • {r.rating}★ • 94% match</p>
              <div className="progress-bar">
                <div className="progress-fill" style={{ width: "94%" }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
