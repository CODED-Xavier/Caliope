import React from "react";

/** A crash inside one part of the screen shows a small message there instead of blanking the whole app. */
export default class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error("Calíope:", error, info?.componentStack); }
  componentDidUpdate(prev) { if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null }); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="error-box">
        <div className="small"><b>{this.props.label || "This part"} hit an error.</b> The rest of Calíope keeps working.</div>
        <div className="tiny muted mono no-tr">{String(this.state.error?.message || this.state.error)}</div>
        <button className="btn small" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}
