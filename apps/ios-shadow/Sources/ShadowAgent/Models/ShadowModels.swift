import Foundation

enum AutonomyMode: String, CaseIterable, Codable, Identifiable { case off, suggestOnly, draftOnly, executeWithApproval, trustedWorkflow, fullAutonomousDisabled; var id: String { rawValue } }
enum RiskClass: String, Codable { case low, medium, high, critical, blocked }
struct MemoryItem: Identifiable, Codable { let id: UUID; var title: String; var snippet: String; var confidence: Double; var source: String }
struct ApprovalRequest: Identifiable, Codable { let id: UUID; var title: String; var reason: String; var risk: RiskClass; var createdAt: Date }
struct Device: Identifiable, Codable { let id: UUID; var name: String; var trusted: Bool; var lastSeen: Date? }
