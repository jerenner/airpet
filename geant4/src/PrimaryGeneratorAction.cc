#include "PrimaryGeneratorAction.hh"

#include "G4GeneralParticleSource.hh"
#include "G4ParticleTable.hh"
#include "G4ParticleDefinition.hh"
#include "G4SystemOfUnits.hh"
#include "G4Event.hh"

PrimaryGeneratorAction::PrimaryGeneratorAction()
 : G4VUserPrimaryGeneratorAction(),
   fGPS(nullptr)
{
  // Instantiate the General Particle Source
  fGPS = new G4GeneralParticleSource();

  // --- Set a reasonable default source ---
  // This can be completely overridden by macro commands.
  // This default is useful for running the application without a macro.

  // Get the particle table
  G4ParticleTable* particleTable = G4ParticleTable::GetParticleTable();
  G4String particleName = "gamma";
  G4ParticleDefinition* particle = particleTable->FindParticle(particleName);

  // Set default particle type
  fGPS->SetParticleDefinition(particle);

  // Get the source definition object
  auto* source = fGPS->GetCurrentSource();

  // Set default energy (monoenergetic)
  source->GetEneDist()->SetMonoEnergy(511. * keV);

  // Set default position (point source at the origin)
  source->GetPosDist()->SetCentreCoords(G4ThreeVector(0., 0., 0.));
  source->GetPosDist()->SetPosDisType("Point");

  // Set default angular distribution (isotropic)
  source->GetAngDist()->SetAngDistType("iso");
}

PrimaryGeneratorAction::~PrimaryGeneratorAction()
{
  delete fGPS;
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* anEvent)
{
  // The G4GeneralParticleSource is configured via UI commands.
  // All we have to do here is tell it to generate the primary vertex.
  // It will do so according to the settings provided in the macro file.
  fGPS->GeneratePrimaryVertex(anEvent);
}