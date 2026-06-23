import Foundation

public protocol AgentMemoryStore: Sendable {
    func save(_ event: UserContextEvent) async throws
    func search(query: String, limit: Int) async throws -> [UserContextEvent]
    func allEvents() async throws -> [UserContextEvent]
}

public actor InMemoryAgentMemoryStore: AgentMemoryStore {
    private var events: [UserContextEvent] = []

    public init() {}

    public func save(_ event: UserContextEvent) async throws {
        events.append(event)
    }

    public func search(query: String, limit: Int) async throws -> [UserContextEvent] {
        let tokens = Set(query.lowercased().split { !$0.isLetter && !$0.isNumber }.map(String.init))
        guard !tokens.isEmpty else { return Array(events.prefix(limit)) }

        let scoredEvents: [(event: UserContextEvent, score: Int)] = events.map { event in
            let searchable = ([event.content] + event.metadata.map { "\($0.key) \($0.value)" }).joined(separator: " ").lowercased()
            let score = tokens.reduce(0) { partialResult, token in
                partialResult + (searchable.contains(token) ? 1 : 0)
            }
            return (event: event, score: score)
        }

        let matches = scoredEvents
            .filter { scoredEvent in scoredEvent.score > 0 }
            .sorted { lhs, rhs in
                if lhs.score == rhs.score { return lhs.event.occurredAt > rhs.event.occurredAt }
                return lhs.score > rhs.score
            }
            .prefix(limit)
            .map { scoredEvent in scoredEvent.event }

        return Array(matches)
    }

    public func allEvents() async throws -> [UserContextEvent] {
        events
    }
}

public actor FileAgentMemoryStore: AgentMemoryStore {
    private let fileURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    public init(fileURL: URL) {
        self.fileURL = fileURL
        self.encoder = JSONEncoder()
        self.encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        self.encoder.dateEncodingStrategy = .iso8601
        self.decoder = JSONDecoder()
        self.decoder.dateDecodingStrategy = .iso8601
    }

    public func save(_ event: UserContextEvent) async throws {
        var events = try loadEvents()
        events.append(event)
        try persist(events)
    }

    public func search(query: String, limit: Int) async throws -> [UserContextEvent] {
        let events = try loadEvents()
        let memory = InMemoryAgentMemoryStore()
        for event in events {
            try await memory.save(event)
        }
        return try await memory.search(query: query, limit: limit)
    }

    public func allEvents() async throws -> [UserContextEvent] {
        try loadEvents()
    }

    private func loadEvents() throws -> [UserContextEvent] {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return [] }
        let data = try Data(contentsOf: fileURL)
        return try decoder.decode([UserContextEvent].self, from: data)
    }

    private func persist(_ events: [UserContextEvent]) throws {
        let directory = fileURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let data = try encoder.encode(events)
        try data.write(to: fileURL, options: [.atomic, .completeFileProtection])
    }
}
