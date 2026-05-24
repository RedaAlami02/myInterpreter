import 'package:appwrite/appwrite.dart';

const String endpoint = 'https://fra.cloud.appwrite.io/v1';
const String projectId = '6a12447800077d5113ae';
const String dbId = 'myinterpreter';

final Client client = Client()
    .setEndpoint(endpoint)
    .setProject(projectId);

final Account account = Account(client);
final Databases databases = Databases(client);
final TablesDB tablesDB = TablesDB(client);
