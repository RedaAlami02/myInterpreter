import 'package:flutter/material.dart';

/// Stable placeholders without motion; announced once to screen readers.
class LoadingRows extends StatelessWidget {
  const LoadingRows({super.key});
  @override
  Widget build(BuildContext context) => Semantics(
    label: 'Chargement en cours',
    liveRegion: true,
    child: ExcludeSemantics(
      child: ListView.builder(
        itemCount: 6,
        itemBuilder: (context, index) => Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                height: 18,
                width: 160,
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
              ),
              const SizedBox(height: 12),
              Container(
                height: 14,
                width: double.infinity,
                color: Theme.of(context).colorScheme.surfaceContainerHigh,
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
