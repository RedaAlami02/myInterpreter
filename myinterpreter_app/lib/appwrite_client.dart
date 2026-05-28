import 'package:appwrite/appwrite.dart';
import 'package:appwrite/models.dart';

const String endpoint = 'https://fra.cloud.appwrite.io/v1';
const String projectId = '6a12447800077d5113ae';
const String dbId = 'myinterpreter';

final Client client = Client()
    .setEndpoint(endpoint)
    .setProject(projectId);

final Account account = Account(client);
final Databases databases = Databases(client);
final TablesDB tablesDB = TablesDB(client);

/// The Appwrite SDK's Document.data reads from map["data"] but the API
/// returns user fields at the top level. This extracts them correctly.
Map<String, dynamic> docFields(Document doc) {
  // Access the underlying map via toMap(), then strip the $ system fields
  final raw = doc.toMap();
  return Map.fromEntries(
    raw.entries.where((e) => !e.key.startsWith('\$') && e.key != 'data'),
  );
}
